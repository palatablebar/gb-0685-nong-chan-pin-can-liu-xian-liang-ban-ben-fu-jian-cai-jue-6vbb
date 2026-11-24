import csv
from decimal import Decimal,InvalidOperation
from pathlib import Path
from app.errors import DomainError
from app.config import FACTOR_REQUIRED
from app.modules.m2_mapping.coerce import SENTINELS

def load_factors():
    path=Path(__file__).resolve().parents[3]/'sample_data'/'factors.csv'
    with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    factors=[]
    for row in rows:
        if any(str(row.get(k,'')).strip().upper() in SENTINELS for k in FACTOR_REQUIRED):
            raise DomainError('FACTOR','因子库必填值缺失')
        try:
            value=Decimal(str(row['factor']).strip())
            if not value.is_finite() or value<=0:raise InvalidOperation
        except InvalidOperation:raise DomainError('FACTOR','加工因子数值无效')
        item={k:row[k].strip() for k in FACTOR_REQUIRED if k!='factor'};item['factor']=str(value)
        factors.append(item)
    return factors

def match_factors(record, analyte, factors):
    # 因子与流程必须同属一个产品范围：原料产品、流程、加工类型、可食部位全部一致。
    scope=[f for f in factors if f['product']==record['raw_product'] and f['flow']==record['flow']
           and f['process_type']==record['process_type'] and f['edible_part']==record['edible_part']]
    hits=[f for f in scope if f['analyte']==analyte]
    if not hits:
        if scope:
            # 同一产品范围登记了其他残留项目的因子，本项目却无对应因子：禁止跨项目/跨范围借用。
            return None,'SCOPE'
        # 加工类型、可食部位或因子在库中完全无法对应。
        return None,'NO_FACTOR'
    if len({f['factor'] for f in hits})>1:return None,'FACTOR_CONFLICT'
    return hits[0],None
