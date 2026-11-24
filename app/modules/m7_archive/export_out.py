import io,csv,json,hashlib

def bundle(state):
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(['记录类型','批次','来源行','业务ID','原因码','内容'])
    rid=state.get('run_id','preview')
    writer.writerow(['运行清单',rid,'','','',json.dumps(state.get('manifest',{}),ensure_ascii=False,sort_keys=True)])
    writer.writerow(['对账',rid,'','','',json.dumps(state.get('reconcile',{}),ensure_ascii=False,sort_keys=True)])
    for row in state.get('calculations',[]):writer.writerow(['计算',rid,row.get('line',''),row.get('id',''),row.get('code',''),json.dumps(row,ensure_ascii=False,sort_keys=True)])
    for row in state['quarantine']:writer.writerow(['隔离',rid,row['line'],row.get('id',''),row['code'],json.dumps(row.get('raw',{}),ensure_ascii=False,sort_keys=True)])
    process=state.get('process')
    if process:
        writer.writerow(['加工对账',rid,'','','',json.dumps({k:v for k,v in process.items() if k not in ('dispositions','release','hold')},ensure_ascii=False,sort_keys=True)])
        for row in process['dispositions']:
            writer.writerow(['加工处置',rid,row.get('line',''),row.get('disposition_id',''),row.get('reason') or row.get('disposition'),json.dumps(row,ensure_ascii=False,sort_keys=True)])
        for row in process['intake'].get('process_quarantine',[]):
            writer.writerow(['加工隔离',rid,row['line'],row.get('id',''),row['code'],json.dumps(row.get('raw',[]),ensure_ascii=False,sort_keys=True)])
    return '\ufeff'+out.getvalue()

def checksum(state):
    return hashlib.sha256(bundle(state).encode('utf-8')).hexdigest()

def process_ledger(state):
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(['处置编号','加工记录行','成品批次','成品产品','原料批次','残留项目','检测方法','处置结论','原因码','判定依据',
        '原料区间(mg/kg)','加工因子','成品推算区间(mg/kg)','成品限量(mg/kg)','限量标准','来源报告ID'])
    process=state.get('process')
    if process:
        for d in process['dispositions']:
            raw_range=('' if d['raw_lower'] is None else str(d['raw_lower'])+'~'+str(d['raw_upper']))
            fin_range=('' if d['finished_lower'] is None else str(d['finished_lower'])+'~'+str(d['finished_upper']))
            writer.writerow([d['disposition_id'],d['line'],d['finished_batch'],d['finished_product'],d['raw_batch'],d['analyte'],
                d['method'],'可发布' if d['disposition']=='RELEASE' else '待重检',d['reason'] or '',d['basis'],
                raw_range,d['factor'] or '',fin_range,d['limit'] or '',d.get('standard_id',''),d['source_report'] or ''])
        for q in process['intake'].get('process_quarantine',[]):
            writer.writerow(['',q['line'],'','','','','','加工记录隔离',q['code'],'QUARANTINE','','','','','',q.get('id','')])
    return '\ufeff'+out.getvalue()
