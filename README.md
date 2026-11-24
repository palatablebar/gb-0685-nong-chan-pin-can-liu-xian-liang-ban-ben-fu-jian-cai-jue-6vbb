# 农产品残留限量版本与复检裁决

面向农产品检测站复核员，处理采信、判定、核算、复核与归档。

## 启动

```bash
docker compose up --build -d
```

访问 http://localhost:18254 。初次启动自动运行脏样例，可切换 clean.csv 与 legacy.csv。顶部“运行批次”会重新计算，同源输入复用批次。

## 业务模块

- 报告采信：`/m1_ingest`、`/api/m1_ingest`
- 项目映射：`/m2_mapping`、`/api/m2_mapping`
- 限量选版：`/m3_versions`、`/api/m3_versions`
- 检出量换算：`/m4_segments`、`/api/m4_segments`
- 复检裁决：`/m5_calculate`、`/api/m5_calculate`
- 批次判级：`/m6_reconcile`、`/api/m6_reconcile`
- 加工处置：`/m8_process`、`/api/m8_process`
- 报告归档：`/m7_archive`、`/api/m7_archive`

## 加工处置规则

原料检测结论不得直接沿用于成品。成品项目只有在加工记录的原料产品、流程、加工类型、可食部位与因子库**同一产品范围**完全对应、且成品限量与方法适用时，才用 `原料区间 × 加工因子` 推算成品区间并按同一区间规则判定：

- 推算 PASS → 可发布（RELEASE）；推算 FAIL/UNCERTAIN → 待重检（HOLD）。
- 加工类型、可食部位或因子无法对应（NO_FACTOR）、同范围因子缺失（SCOPE）、因子不唯一（FACTOR_CONFLICT）、成品限量/方法无法对应（NO_LIMIT/METHOD）、原料证据缺失（NO_EVIDENCE）：只进待重检，保留原料证据，不给成品结论。
- 重跑同一加工来源幂等，不新增处置项、不新增留痕版本；处置中断可在 `/m8_process` 恢复任一旧版，原始原料与加工记录保留。
- 加工处置账可在工作台下载：`/api/archive/<run_id>/process-ledger.csv`（加工对账未平拒绝下载）；完整封存账 `export.csv` 同时含原料计算、加工处置与两类隔离，项目结论与归档只认封存账这一版。

## 核心规则

按采样日期选择有效限量，低于检出限保留区间；复检不得越过样本关联与方法适用范围。完整数值、边界和异常定义见 `docs/DATA-DICTIONARY.md`。

## 验证

```bash
docker compose exec -T app pytest -q
docker compose config --quiet
```

原始样例在 `sample_data/`（加工记录 `process.csv`、加工因子库 `factors.csv`，成品限量追加在 `limits.csv`）。测试在 `tests/`。封存文件是单份CSV，含运行清单、计算证据、加工处置、隔离原因与对账。复核需提交当前版本，陈旧复核返回409。

## 数据与限制

SQLite保存在records命名卷，普通重启与构建不会清除。确认可丢弃本项目数据后，运行 `docker compose down -v` 再启动可重置。单文件上限2MB；不接入外部业务系统；历史规则由本项目样例定义，不代表实际行业标准。
