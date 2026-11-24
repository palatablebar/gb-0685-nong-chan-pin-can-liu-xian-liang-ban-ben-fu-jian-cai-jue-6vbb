import csv,io
from app.errors import DomainError
from app.config import PROCESS_REQUIRED,PROCESS_DATES
from app.modules.m1_ingest.decode import decode
from app.modules.m2_mapping.coerce import day,SENTINELS

def read_process(raw):
    text,encoding=decode(raw)
    if not text:raise DomainError('EMPTY_FILE','加工文件为空')
    if not text.strip():raise DomainError('BLANK_FILE','加工文件仅含空行')
    reader=csv.reader(io.StringIO(text,newline=''))
    try:header=[s.strip().lstrip('\ufeff') for s in next(reader)]
    except (StopIteration,csv.Error):raise DomainError('HEADER','无法读取加工表头')
    if len(set(header))!=len(header) or not set(PROCESS_REQUIRED)<=set(header):
        raise DomainError('HEADER','加工表头缺失或重复')
    out={'process_rows':[],'process_quarantine':[],'process_input':0,'process_blank':0,'process_headers':0,'process_duplicates':0,'encoding':encoding}
    try:
        for row in reader:
            out['process_input']+=1;line=reader.line_num
            if not row or not any(s.strip() for s in row):out['process_blank']+=1;continue
            if row==header:out['process_headers']+=1;continue
            if len(row)!=len(header):
                out['process_quarantine'].append({'line':line,'id':'','code':'WIDTH','raw':row});continue
            item=dict(zip(header,row));item['_line']=line;item['_raw']=dict(item)
            out['process_rows'].append(item)
    except csv.Error as exc:raise DomainError('CSV',str(exc))
    if out['process_input']==0:raise DomainError('HEADER_ONLY','加工文件仅含表头')
    good=[];groups={};rejected=set()
    for item in out['process_rows']:
        try:
            for field in PROCESS_REQUIRED:
                if str(item.get(field,'')).strip().upper() in SENTINELS:raise DomainError('MISSING','加工必填值缺失')
            for field in PROCESS_DATES:
                item[field]=day(item[field])
            groups.setdefault(item['process_id'],[]).append(item)
        except DomainError as error:
            rejected.add(item['_line'])
            out['process_quarantine'].append({'line':item['_line'],'id':item.get('process_id',''),'code':error.code,'raw':item['_raw']})
    for pid,rows in groups.items():
        unique={str(sorted((k,str(v)) for k,v in r.items() if not k.startswith('_'))) for r in rows}
        if len(unique)>1:
            for r in rows:
                rejected.add(r['_line'])
                out['process_quarantine'].append({'line':r['_line'],'id':pid,'code':'CONFLICT','raw':r['_raw']})
        else:
            good.append(rows[0]);out['process_duplicates']+=len(rows)-1
    out['process_rows']=good
    # 对账恒等式（与原料账同口径）：输入行 = 采纳 + 隔离 + 空行 + 重复表头 + 完全重复。
    out['process_balanced']=(out['process_input']==len(good)+len(out['process_quarantine'])
        +out['process_blank']+out['process_headers']+out['process_duplicates'])
    return out
