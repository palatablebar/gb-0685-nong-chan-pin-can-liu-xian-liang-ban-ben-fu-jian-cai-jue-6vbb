import csv,io
from copy import deepcopy
from app.workflow import load,run
from app.modules.m8_process.rules import apply
from app.modules.m7_archive.export_out import process_ledger,bundle

def _by_id(state):return {d['disposition_id']:d for d in state['process']['dispositions']}

def test_process_balance_conservation(state):
    p=state['process'];i=p['intake']
    accepted=i['process_input']-len(i['process_quarantine'])-i['process_blank']-i['process_headers']-i['process_duplicates']
    # 输入行（表头不计）= 采纳 + 隔离 + 空行 + 重复表头 + 完全重复，与原料账同一口径。
    assert i['process_input']==accepted+len(i['process_quarantine'])+i['process_blank']+i['process_headers']+i['process_duplicates']
    assert p['balanced'] is True
    assert accepted==9  # process.csv 九条有效加工记录

def test_release_uses_process_factor_within_same_scope(state):
    d=_by_id(state)['PR001-P01']
    # 烘干因子0.5来自同一产品范围（苹果|烘干线A|烘干|全果），区间 0.004*0.5=0.002 ≤ 0.005 可发布。
    assert d['disposition']=='RELEASE' and d['factor']=='0.5'
    assert d['finished_lower']=='0.0020' and d['finished_upper']=='0.0020'
    assert d['limit']=='0.005' and d['basis']=='PROCESS_FACTOR'
    assert d['factor_scope']=='苹果|烘干线A|烘干|全果'

def test_concentration_factor_amplifies_and_fails(state):
    d=_by_id(state)['PR009-P02']
    # 浓缩因子2，原料 0.03 → 0.06，超过成品限量0.02，不得发布。
    assert d['disposition']=='HOLD' and d['reason']=='DERIVED_FAIL'
    assert d['finished_upper']=='0.060' and d['limit']=='0.02'

def test_unmapped_process_type_holds_with_raw_evidence(state):
    # PR006 冻干在因子库无任何对应：保留原料证据，不给成品结论。
    d=_by_id(state)['PR006-P01']
    assert d['disposition']=='HOLD' and d['reason']=='NO_FACTOR'
    assert d['basis']=='RAW_EVIDENCE_ONLY' and d['finished_lower'] is None and d['raw_upper']=='0.004'

def test_scope_mismatch_holds_even_when_other_flow_factor_exists(state):
    # 烘干线C在因子库完全无登记 → NO_FACTOR；同范围其他项目有因子而本项目缺失 → SCOPE，均不得借用。
    d=_by_id(state)['PR007-P01']
    assert d['disposition']=='HOLD' and d['reason']=='NO_FACTOR' and d['factor'] is None
    d2=_by_id(state)['PR001-P02']
    # 烘干线A/全果仅登记P01因子，P02禁止借用，且因方法适用范围同样受限先判METHOD之外的因子缺失。
    assert d2['disposition']=='HOLD' and d2['reason'] in ('SCOPE','METHOD')
    # 果渣部位只有P01因子，P02无法对应。
    d3=_by_id(state)['PR005-P02']
    assert d3['reason']=='SCOPE' and d3['disposition']=='HOLD'

def test_method_out_of_finished_standard_holds(state):
    # PR003-P02 因子可对应（清汁P02=2），但GC-MS不在苹果清汁P02限量标准的方法范围内。
    d=_by_id(state)['PR003-P02']
    assert d['disposition']=='HOLD' and d['reason']=='METHOD' and d['finished_lower'] is None

def test_missing_raw_batch_evidence_holds(state):
    # B901 原料批已被隔离，无任何采纳证据：只进待重检，不发布。
    d=_by_id(state)['PR008-P01']
    assert d['disposition']=='HOLD' and d['reason']=='NO_EVIDENCE' and d['source_report'] is None

def test_width_row_quarantined_not_disposed(state):
    q=state['process']['intake']['process_quarantine']
    assert any(x['code']=='WIDTH' and x['line']==11 for x in q)
    assert all(x['process_id']!='PR010' for x in state['process']['dispositions'])

def test_missing_field_quarantined_and_balanced():
    raw=load('dirty.csv')
    custom="""﻿process_id,raw_batch,finished_batch,raw_product,finished_product,flow,process_type,edible_part,processed,method
PR1,B001,FP1,苹果,苹果干,烘干线A,烘干,全果,2026-08-05,LC-MS/MS
PR2,B001,FP2,苹果,苹果干,烘干线A,烘干,全果,-,LC-MS/MS
"""
    s=run(raw,{'process_csv':custom})
    q=s['process']['intake']['process_quarantine']
    assert any(x['code']=='MISSING' and x['id']=='PR2' for x in q)
    assert s['process']['balanced'] is True
    assert {d['process_id'] for d in s['process']['dispositions']}=={'PR1'}

def test_no_new_disposition_on_rerun_same_source(state):
    again=run(load('dirty.csv'),{})
    assert again['run_id']==state['run_id']
    assert [d['disposition_id'] for d in again['process']['dispositions']]== \
           [d['disposition_id'] for d in state['process']['dispositions']]

def test_duplicate_process_record_adds_no_disposition():
    raw=load('dirty.csv')
    dup="""﻿process_id,raw_batch,finished_batch,raw_product,finished_product,flow,process_type,edible_part,processed,method
PR001,B001,FP001,苹果,苹果干,烘干线A,烘干,全果,2026-08-05,LC-MS/MS
PR001,B001,FP001,苹果,苹果干,烘干线A,烘干,全果,2026-08-05,LC-MS/MS
"""
    s=run(raw,{'process_csv':dup})
    ids=[d['disposition_id'] for d in s['process']['dispositions']]
    assert ids==['PR001-P01','PR001-P02'] and s['process']['intake']['process_duplicates']==1

def test_conflicting_process_duplicates_quarantined():
    raw=load('dirty.csv')
    dup="""﻿process_id,raw_batch,finished_batch,raw_product,finished_product,flow,process_type,edible_part,processed,method
PR001,B001,FP001,苹果,苹果干,烘干线A,烘干,全果,2026-08-05,LC-MS/MS
PR001,B001,FP001,苹果,苹果干,烘干线A,烘干,全果,2026-08-06,LC-MS/MS
"""
    s=run(raw,{'process_csv':dup})
    assert any(q['id']=='PR001' and q['code']=='CONFLICT' for q in s['process']['intake']['process_quarantine'])
    assert s['process']['dispositions']==[]

def test_interval_uncertain_derivation_holds(tmp_path,monkeypatch):
    # 原料不确定区间 [0,0.01) × 因子1 = [0,0.01)，相对成品限量0.005：下界不超限、上界超限 → UNCERTAIN，待重检。
    raw_csv="""﻿id,sample_id,batch,product,analyte,method,version,sampled,reported,result,unit,lod,relation,note
00101,S101,B100,苹果,P01,LC-MS/MS,1,2026-08-01,2026-08-02,<0.01,mg/kg,0.01,,初检
"""
    process_csv="""﻿process_id,raw_batch,finished_batch,raw_product,finished_product,flow,process_type,edible_part,processed,method
PR100,B100,FP100,苹果,苹果干,实验线Z,实验,全果,2026-08-05,LC-MS/MS
"""
    from app.modules.m8_process import rules as m8
    original=m8.load_factors
    m8.load_factors=lambda: original()+[{'product':'苹果','flow':'实验线Z','process_type':'实验','edible_part':'全果','analyte':'P01','factor':'1'}]
    try:
        s=run(raw_csv.encode('utf-8'),{'process_csv':process_csv})
    finally:
        m8.load_factors=original
    d=[d for d in s['process']['dispositions'] if d['process_id']=='PR100' and d['analyte']=='P01'][0]
    assert d['disposition']=='HOLD' and d['reason']=='DERIVED_UNCERTAIN'
    assert d['finished_lower']=='0' and d['finished_upper']=='0.01'

def test_ledger_download_rows(state):
    text=process_ledger(state).lstrip('﻿')
    rows=list(csv.reader(io.StringIO(text)))
    assert rows[0][0]=='处置编号' and rows[0][7]=='处置结论'
    body={r[0]:r for r in rows[1:] if r[0]}
    assert body['PR001-P01'][7]=='可发布' and body['PR008-P01'][7]=='待重检'

def test_archive_bundle_contains_process_section(state):
    text=bundle(state)
    assert '加工处置' in text and '加工对账' in text and 'PR001-P01' in text

def test_archive_ready_requires_process_balance(state):
    assert state['archive']['ready'] is True and state['archive']['process_ready'] is True
    broken=deepcopy(state);broken['process']['balanced']=False
    from app.modules.m7_archive.service import execute
    out=execute(broken)
    assert out['archive']['ready'] is False and out['archive']['process_ready'] is False

def test_finished_limit_halfopen_by_processed_date():
    # 加工日落入限量空窗（2027-01-01之后无标准）→ NO_LIMIT 待重检。
    raw=load('dirty.csv')
    custom="""﻿process_id,raw_batch,finished_batch,raw_product,finished_product,flow,process_type,edible_part,processed,method
PR200,B001,FP200,苹果,苹果干,烘干线A,烘干,全果,2027-02-01,LC-MS/MS
"""
    s=run(raw,{'process_csv':custom})
    d=[d for d in s['process']['dispositions'] if d['process_id']=='PR200'][0]
    assert d['reason']=='NO_LIMIT' and d['disposition']=='HOLD'

def test_factor_conflict_quarantines_from_release():
    from app.modules.m8_process.factors import match_factors
    record={'raw_product':'苹果','flow':'烘干线A','process_type':'烘干','edible_part':'全果'}
    factors=[
        {'product':'苹果','flow':'烘干线A','process_type':'烘干','edible_part':'全果','analyte':'P01','factor':'0.5'},
        {'product':'苹果','flow':'烘干线A','process_type':'烘干','edible_part':'全果','analyte':'P01','factor':'0.9'}]
    factor,reason=match_factors(record,'P01',factors)
    assert factor is None and reason=='FACTOR_CONFLICT'

def test_factor_must_share_full_product_scope():
    from app.modules.m8_process.factors import match_factors
    record={'raw_product':'苹果','flow':'烘干线A','process_type':'烘干','edible_part':'全果'}
    # 只有别的流程/别的部位存在因子时，本范围因子无法对应 → NO_FACTOR，不得借用。
    foreign=[{'product':'苹果','flow':'浓缩线B','process_type':'浓缩','edible_part':'清汁','analyte':'P01','factor':'2'}]
    assert match_factors(record,'P01',foreign)==(None,'NO_FACTOR')
    # 同范围登记了其他项目因子、本项目缺失 → SCOPE。
    sibling=[{'product':'苹果','flow':'烘干线A','process_type':'烘干','edible_part':'全果','analyte':'P02','factor':'0.5'}]
    assert match_factors(record,'P01',sibling)==(None,'SCOPE')

def test_process_version_trace_and_restore(state,tmp_path,monkeypatch):
    # 处置中断恢复旧版：同一 run 重跑留痕，回滚后处置账回到旧版，原料与加工记录保留。
    monkeypatch.setenv('DB_PATH',str(tmp_path/'p.db'))
    from app import store
    store.save(state['run_id'],state)
    assert [v['version'] for v in store.process_versions(state['run_id'])]==[1]
    # 同加工来源重跑、处置账内容不变：不新增留痕版本（重跑不得新增处置项）。
    store.save(state['run_id'],state)
    assert [v['version'] for v in store.process_versions(state['run_id'])]==[1]
    # 模拟处置中断后处置账被破坏（现场为空）。
    broken=store.get(state['run_id']);broken['process']['dispositions']=[]
    import sqlite3,json,os
    con=sqlite3.connect(os.environ['DB_PATH']);con.execute('UPDATE runs SET body=? WHERE id=?',
        (json.dumps(broken,ensure_ascii=False),state['run_id']));con.commit();con.close()
    assert store.get(state['run_id'])['process']['dispositions']==[]
    # 恢复到第1版；恢复动作本身追加一条留痕（第2版）。
    restored=store.restore_process(state['run_id'],1)
    assert len(restored['process']['dispositions'])==len(state['process']['dispositions'])
    assert [v['version'] for v in store.process_versions(state['run_id'])]==[1,2]
    # 原料计算证据未被删除。
    assert restored['calculations']==state['calculations']

def test_restore_unknown_version_404(state,tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'p2.db'))
    from app import store
    from app.errors import DomainError
    store.save(state['run_id'],state)
    try:
        store.restore_process(state['run_id'],99)
        assert False
    except DomainError as e:
        assert e.status==404

def test_conflicting_raw_evidence_holds(state):
    # 同一原料批次同项目两条互相矛盾的采纳结论时，不得任选一条推算，判 EVIDENCE_CONFLICT。
    s=deepcopy(state)
    dup=dict(s['calculations'][0]);dup['id']='99999';dup['lower']='0.999';dup['upper']='0.999'
    s['calculations'].append(dup)
    from app.modules.m8_process.rules import apply
    out=apply(s)
    hit=[d for d in out['process']['dispositions'] if d['raw_batch']==dup['batch'] and d['analyte']==dup['analyte']]
    assert all(d['reason']=='EVIDENCE_CONFLICT' and d['disposition']=='HOLD' for d in hit)
