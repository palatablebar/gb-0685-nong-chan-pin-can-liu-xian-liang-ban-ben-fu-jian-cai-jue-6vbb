import sqlite3,json,os
from pathlib import Path
from app.errors import DomainError

def connection():
    path=Path(os.environ.get('DB_PATH','data/records.db'));path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=10);db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, body TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, decision TEXT NOT NULL DEFAULT "待复核")')
    db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    # 加工处置账按 (run, 处置版本) 留痕，中断时回滚到上一版；原始原料与加工记录随 body 一并保留。
    db.execute('CREATE TABLE IF NOT EXISTS process_versions (run_id TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL DEFAULT (datetime(\'now\')), PRIMARY KEY(run_id,version))')
    return db

def save(run_id, body):
    with connection() as db:
        db.execute('INSERT OR IGNORE INTO runs(id,body) VALUES (?,?)',(run_id,json.dumps(body,ensure_ascii=False)))
        if body.get('process'):
            # 重跑同一加工来源：处置账内容不变时不新增留痕版本（处置项不得新增）。
            payload=json.dumps(body.get('process'),ensure_ascii=False,sort_keys=True)
            last=db.execute('SELECT body FROM process_versions WHERE run_id=? ORDER BY version DESC LIMIT 1',(run_id,)).fetchone()
            if last is None or json.dumps(json.loads(last['body']),ensure_ascii=False,sort_keys=True)!=payload:
                row=db.execute('SELECT COALESCE(MAX(version),0)+1 AS v FROM process_versions WHERE run_id=?',(run_id,)).fetchone()
                db.execute('INSERT INTO process_versions(run_id,version,body) VALUES (?,?,?)',(run_id,row['v'],payload))
        db.execute("INSERT INTO meta(key,value) VALUES ('latest',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(run_id,))
    return get(run_id)

def get(run_id):
    with connection() as db:r=db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
    if not r:raise DomainError('NOT_FOUND','批次不存在',404)
    body=json.loads(r['body']);body.update(run_id=r['id'],review_version=r['version'],decision=r['decision']);return body

def history():
    with connection() as db:rows=db.execute("SELECT id,version,decision FROM runs ORDER BY CASE WHEN id=(SELECT value FROM meta WHERE key='latest') THEN 0 ELSE 1 END,rowid DESC LIMIT 100").fetchall()
    return [dict(r) for r in rows]

def review(run_id, version, decision):
    if decision not in ('通过','退回'):raise DomainError('DECISION','复核状态无效')
    with connection() as db:
        cur=db.execute('UPDATE runs SET version=version+1,decision=? WHERE id=? AND version=?',(decision,run_id,version))
        if cur.rowcount!=1:
            if not db.execute('SELECT 1 FROM runs WHERE id=?',(run_id,)).fetchone():raise DomainError('NOT_FOUND','批次不存在',404)
            raise DomainError('STALE','复核版本已更新，请刷新',409)
    return get(run_id)

def process_versions(run_id):
    with connection() as db:
        if not db.execute('SELECT 1 FROM runs WHERE id=?',(run_id,)).fetchone():raise DomainError('NOT_FOUND','批次不存在',404)
        rows=db.execute('SELECT version,created FROM process_versions WHERE run_id=? ORDER BY version',(run_id,)).fetchall()
    return [dict(r) for r in rows]

def restore_process(run_id, version):
    # 处置中断恢复：用指定旧版处置账覆盖当前版，原始原料证据与加工记录不删除。
    with connection() as db:
        target=db.execute('SELECT body FROM process_versions WHERE run_id=? AND version=?',(run_id,version)).fetchone()
        if not target:raise DomainError('NOT_FOUND','处置版本不存在',404)
        run=db.execute('SELECT body FROM runs WHERE id=?',(run_id,)).fetchone()
        if not run:raise DomainError('NOT_FOUND','批次不存在',404)
        body=json.loads(run['body']);body['process']=json.loads(target['body'])
        db.execute('UPDATE runs SET body=? WHERE id=?',(json.dumps(body,ensure_ascii=False),run_id))
        row=db.execute('SELECT COALESCE(MAX(version),0)+1 AS v FROM process_versions WHERE run_id=?',(run_id,)).fetchone()
        db.execute('INSERT INTO process_versions(run_id,version,body) VALUES (?,?,?)',
            (run_id,row['v'],target['body']))
    return get(run_id)
