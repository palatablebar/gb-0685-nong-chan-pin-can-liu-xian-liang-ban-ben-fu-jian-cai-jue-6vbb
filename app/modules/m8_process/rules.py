from collections import defaultdict
from pathlib import Path
from decimal import Decimal
from app.config import PROCESS_SAMPLE
from app.modules.m3_versions.standards import standards
from app.modules.m8_process.factors import load_factors,match_factors
from app.modules.m8_process.reader import read_process

def default_process_bytes():
    return (Path(__file__).resolve().parents[3]/'sample_data'/PROCESS_SAMPLE).read_bytes()

def choose_finished_limit(row, limits):
    # 成品限量按加工完成日落在半开区间 [start,end) 内选择，与采样日选版规则一致。
    candidates=[l for l in limits if l['product']==row['finished_product'] and l['analyte']==row['analyte']
                and l['start']<=row['processed']<l['end']]
    if len(candidates)!=1:return None,'NO_LIMIT'
    limit=candidates[0]
    if row['method'] not in limit['methods'].split('|'):return None,'METHOD'
    return limit,None

def hold(record, analyte, reason, calc=None, factor=None):
    item={'disposition_id':record['process_id']+'-'+analyte,'process_id':record['process_id'],'line':record['_line'],
          'finished_batch':record['finished_batch'],'finished_product':record['finished_product'],
          'raw_batch':record['raw_batch'],'analyte':analyte,'method':record['method'],
          'disposition':'HOLD','reason':reason,
          'source_report':calc['id'] if calc else None,'basis':'RAW_EVIDENCE_ONLY',
          'raw_lower':calc['lower'] if calc else None,'raw_upper':calc['upper'] if calc else None,
          'finished_lower':None,'finished_upper':None,'limit':None,
          'factor':factor['factor'] if factor else None}
    return item

def derive(record, calc, factor, limit):
    f=Decimal(factor['factor']);lower=Decimal(calc['lower'])*f;upper=Decimal(calc['upper'])*f
    threshold=Decimal(limit['limit_mgkg'])
    # 沿用区间判定：上界（含）≤限量为PASS，下界>限量为FAIL，其余UNCERTAIN。
    code='PASS' if upper<=threshold else 'FAIL' if lower>threshold else 'UNCERTAIN'
    return {'disposition_id':record['process_id']+'-'+calc['analyte'],'process_id':record['process_id'],'line':record['_line'],
            'finished_batch':record['finished_batch'],'finished_product':record['finished_product'],
            'raw_batch':record['raw_batch'],'analyte':calc['analyte'],'method':record['method'],
            'disposition':'RELEASE' if code=='PASS' else 'HOLD',
            'reason':None if code=='PASS' else ('DERIVED_FAIL' if code=='FAIL' else 'DERIVED_UNCERTAIN'),
            'source_report':calc['id'],'basis':'PROCESS_FACTOR',
            'raw_lower':calc['lower'],'raw_upper':calc['upper'],
            'finished_lower':str(lower),'finished_upper':str(upper),'upper_exclusive':bool(calc.get('upper_exclusive')),
            'limit':str(threshold),'factor':factor['factor'],
            'factor_scope':factor['product']+'|'+factor['flow']+'|'+factor['process_type']+'|'+factor['edible_part'],
            'standard_id':limit['id'],'code':code}

def apply(state):
    raw=state.get('parameters',{}).get('process_csv')
    content=raw.encode('utf-8') if isinstance(raw,str) else default_process_bytes()
    intake=read_process(content)
    factors=load_factors();limits=standards()
    # 原料证据按 (原料批次, 残留项目) 汇总，取 M5 复检链收敛后的最终项目结论。
    evidence=defaultdict(list)
    for calc in state.get('calculations',[]):evidence[(calc['batch'],calc['analyte'])].append(calc)
    universe=sorted({calc['analyte'] for calc in state.get('calculations',[])})
    dispositions=[];seen=set()
    for record in intake['process_rows']:
        for analyte in universe:
            # 同一加工来源+项目只允许一条处置项，重跑不得新增。
            dkey=(record['process_id'],analyte)
            if dkey in seen:continue
            seen.add(dkey)
            calcs=evidence.get((record['raw_batch'],analyte),[])
            if not calcs:
                # 原料证据缺失或已被隔离：保留来源信息，只进待重检，不发布。
                dispositions.append(hold(record,analyte,'NO_EVIDENCE'));continue
            if len({(c['lower'],c['upper']) for c in calcs})>1:
                # 同批次同项目出现互相矛盾的原料结论，不得任选一条推算。
                dispositions.append(hold(record,analyte,'EVIDENCE_CONFLICT',sorted(calcs,key=lambda c:c['id'])[0]));continue
            calc=sorted(calcs,key=lambda c:c['id'])[0]
            factor,ferr=match_factors(record,analyte,factors)
            if ferr:
                # 加工类型/可食部位/因子无法对应，或因子与流程不属同一产品范围：保留原料证据，不给成品结论。
                dispositions.append(hold(record,analyte,ferr,calc));continue
            limit,lerr=choose_finished_limit({**record,'analyte':analyte},limits)
            if lerr:
                dispositions.append(hold(record,analyte,lerr,calc,factor));continue
            dispositions.append(derive(record,calc,factor,limit))
    released=[d for d in dispositions if d['disposition']=='RELEASE']
    holding=[d for d in dispositions if d['disposition']=='HOLD']
    state['process']={'intake':{k:v for k,v in intake.items() if k!='process_rows'},
        'dispositions':dispositions,'release':released,'hold':holding,
        'business':{'total':len(dispositions),'release':len(released),'hold':len(holding),'unit':'成品项目'},
        'balanced':intake['process_balanced']}
    return state
