# W04 产出物契约

版本：`demo_run` 为 `w04-0.3.0`，其余三份为 `w04-0.1.0`。四份 JSON Schema 使用 Draft 2020-12。`cleaning_rules.yaml` 先用 YAML 安全解析器解析，再按 `cleaning_rules.schema.json` 校验。`.valid`、`.invalid` 文件是人工结构示例，用于说明结构；实际结果应由程序运行生成。YAML 示例采用 YAML 兼容的 JSON 写法。

## 字段与技术主线对照

| 产出物 | 技术主线与数据设计要求 | 字段 |
| --- | --- | --- |
| profile_report | 逐字段类型、缺失、分布或范围 | fields[].inferred_type、missing_count、total_count、distribution／range |
| profile_report | 异常及证据查询或样本记录序号 | anomalies[].pattern、evidence.query 或 source_file＋sample_rows |
| profile_report | 字典说法、实际情况、影响 | dictionary_differences[] |
| cleaning_rules | 标签与备注清洗，保护合法连字符和完整备注 | tag_cleaning |
| cleaning_rules | 无效值及异常记录处理 | invalid_values、abnormal_records |
| cleaning_rules | 原始文件、备注原文、隔离记录保留 | raw_preservation |
| adapter_test_report | 客户字段映射 | field_mapping[] |
| adapter_test_report | 读入、接受、隔离、去重及对账 | record_counts[]、reconciliation |
| adapter_test_report | 至少一条合法和失败记录的去向 | samples[]，同时包含 accepted 和 quarantined／rejected |
| adapter_test_report | 重复导入前后行数、实际测试结果 | repeat_import、test_result |
| demo_run | 所选链路、实际提问、回答、查询、结果 | selected_chain、runs[].question／agent_answer／actual_queries |
| demo_run | bad case 及原因 | runs[].bad_case、bad_case_reason |
| demo_run | 数据版本与查询库版本 | data_version、query_library_version |

Schema 只检查结构，不把计数声明、对账标记或示例通过当成业务正确性的证明。失败或未执行查询的 demo 允许 actual_queries 为空，以如实记录；executed 必须有查询记录。bad case 必须写原因。CSV 来源行均为不含表头、从 1 起的记录序号，不是物理行号。

## data_diagnosis.md 必备章节

1. 数据范围、版本、覆盖期与来源。
2. 逐字段剖析、异常模式、字典差异及证据位置；字典差异按字典过时、映射错误、数据暂缺归类，写明影响、修订对象和取证对象。
3. 清洗与隔离决定、合法信息和原文保留、对账结果。
4. 至少一项小林工作账与 CRM 的对照；建议核对勿扰名单与触达限制备注。
5. 区分数据结论、访谈依据、推断和待核事项，说明来源缺口及能力边界。
6. 下一步核实清单。

## demo_plan.md 必备章节

1. 首个 demo 的链路和选择理由。
2. 数据可用性、最小验证链路和已有证据。
3. 暂不覆盖范围及待验证条件。
4. 实际运行记录入口、bad case 及下一步处理。
5. FDE 思维判断说明：关键假设、最小验证链路与选择依据、已有证据与待验证条件，以及继续／缩小范围／调整方向的条件。

上述判断说明只作为文档章节要求，不增加机器字段，不作自动判定。AI 模拟客户走查不列为必交。

## 导入契约

基础输入为 members.csv、orders.csv、stores.csv、cards.csv，使用 W03 查询库的列和类型。W04 在同一个 DuckDB 查询库中支持下列可选扩展。小林工作账用于对照核查，不导入查询库。

| 文件或表 | 扩展列及约定 |
| --- | --- |
| members.csv | account_status：活跃、冻结、注销、未激活；registered_channel：门店、小程序、商城、系统导入；created_at：本地 ISO 日期。每列可独立缺省，提供时按约定检查 |
| orders.csv | channel 支持门店、小程序、商城；其他基础列和类型沿用 W03 |
| member_tags.csv | member_id、tag；同一会员同一标签只出现一次；加载器不校验业务标签取值，适配器按客户确认清单拆分 |
| member_notes.csv | member_id、source_file、source_row、source_field、raw_text、note_text、category；source_field 填真实原字段名，青禾为 tag，梧桐为“备注标签”；raw_text 保留该字段完整原值 |
| quarantine.csv | record_type、source_file、source_row、reason_code、raw_json；record_type 为 member、order、card、shop，raw_json 是完整原记录对象 |

member_tags 只放经客户确认的标准标签，标签清单以字典和客户访谈为准；未经确认的暂定标签在诊断报告中列为待核实。其余内容作为备注进入 member_notes：note_text 是一条完整的备注，不拆成碎片；raw_text 保留来源字段完整原值。类别按意思判定，无法归类才用“其他”。checker 严格检查标签集合、非标签文字没有遗漏、raw_text 与来源完整保留、触达限制全部识别。按同一来源记录的原顺序拼接 note_text 后，去掉分隔用的标点和空白进行文字核对；备注分段边界和非触达类别交教师按 rubric 审阅，不做机器判定。

备注 category 支持触达限制、客户关系、卡务、联系状态、其他。备注组合键为 member_id＋source_file＋source_row＋source_field＋note_text；一条来源可拆出多条备注。隔离记录以 source_file＋source_row 唯一定位。source_file 必须为保留的原始文件名；source_row 从 1 起，不含表头，按 CSV 记录计数；source_field 非空。存在可选文件时，导入为 raw_member_tags、raw_member_notes、raw_quarantine，并建立对应同名视图；缺少文件时不创建对应表。

manifest 的 contract_version 可声明为 w04-data-0.1.0；提供新增列或可选文件时也会启用扩展检查。至少提供：

- id、coverage（开始日期和不含结束日期）、reference_date、timezone；
- counts：实际写出的各表行数，sha256：清洗 CSV 文件名与 SHA-256；
- source_sha256：完整保留的原始 CSV 文件名与 SHA-256；
- record_counts：member、order、card、shop 四类记录的 read、accepted、quarantined、deduplicated 非负整数，逐类满足 read＝accepted＋quarantined＋deduplicated。accepted 与导入表行数一致，quarantined 与隔离文件的对应类别行数一致；完全重复行去重后仅计 deduplicated。

加载器校验列、主键、关联、日期、金额类型、文件哈希和实际行数。它不替代字段映射或清洗，不替适配器核实未传入的原始文件内容。失败时保留诊断；重复全量导入使用新项目目录，不能在旧库追加。没有扩展的 W03 四表输入保持原接口。

reason_code 至少能表示孤儿关联、超额退款、契约外卡种、无效日期和主键冲突；已提供 UNLINKED_ACCOUNT、REFUND_EXCEEDS_PAID、UNSUPPORTED_CARD_TYPE、INVALID_DATE、DUPLICATE_PRIMARY_KEY。其他非空原因可由规则明确定义。

覆盖说明 coverage_notes 由适配器写入 manifest：

```json
{"coverage_notes":{"source":"本次只含新 CRM 导出，未包含旧 POS。","time_range":{"start":"2024-09-01","end_exclusive":"2026-09-01"},"quarantined":{"member":0,"order":3,"card":1,"shop":0}}}
```

source 是非空字符串，time_range 的两项为有效 ISO 日期，quarantined 至少包含四类记录的非负整数。额外说明可以保留。查询结果会原样带出覆盖说明；它不能扩大原有时间覆盖范围，也不能把未导出的来源当零。加载器只检查格式，说明的内容和回答的结论范围仍需核对。

## 调优前后的关联

demo_run 至少有一条 runs 记录带 tuning。该 runs 记录本身是调优后的运行，tuning.before 是调优前的运行，两次运行共享外层唯一的 question；before 不再接受另一个 question，避免两次运行实际使用不同问题却声称同题比较。修改位置 change_location 仅可为协议、数据／SQL、工具、提示词／上下文、Harness 策略，同时记录 change 和 reason。

前后都须保留回答、查询状态、实际查询／结果与 bad case 原因。调优可以没有改善，不强制 after 成功；不得删除失败证据。结构示例不是真实调优记录。

## 业务模型接续与 model_changes.md 必备章节

将 W03 的 `docs/w03/business_model.md` 复制到 `docs/w04/business_model.md`，保留自然语言完整模型，不重新规定章节或机器结构。使用 W03 checkpoint 时，复制其中的 `w03-reference/business_model.md` 并注明来源。W03 原提交保留。

根据本周数据与访谈核对模型，只修订受影响的概念、关系和业务规则；核对后无需修改的说明结果，不为凑修改条数而改。纯格式问题交给适配规则处理，证据不足保留待核。模型与指标定义应一致，下一周承接 W04 最新模型。

`model_changes.md` 必备章节：

1. 承接版本、核对范围与结果。
2. 逐项修订前与修订后；没有修订也应明确说明。
3. 证据依据、来源与关联指标的一致性；可引用诊断报告及指标修订记录。
4. 待核事项与下一步核实；没有待核项时明确说明。

预检只检查业务模型文件存在且非空、修订记录必备章节存在，不自动评价业务模型正确性、修改条数或证据质量；这些由助教人工审阅。初始化提供四份文档模板，业务模型须另从 W03 成果或 checkpoint 复制，不用空白模板代替原模型。

## metric_changes.md 必备章节

1. 本次修订的指标 ID 清单；没有修订也应明确说明。
2. 逐项列出修订前的定义、修订后的定义。
3. 每项修订的依据与来源，说明变更原因和适用范围；涉及业务模型修订时引用 model_changes.md 对应条目，核对两者一致性。
可选：附相关影响与复测记录入口。

## 代码类交付物

剖析脚本、适配器源码放在 customer/ 下。checker 在固定样本上实际重跑代码，核对关键异常、合法信息保留、错误记录去向、重复运行及对账。重复运行逐字节比较两次写出的清洗 CSV，输出须按确定顺序写出，不要依赖 set 的迭代顺序；不一致时，预检报告的 repeat 层列出不一致的文件名。JSON 报告只是运行证据，不能代替可运行代码或重跑结果。运行接口见 `tools/w04.py`，完整独立例题见 `examples/w04/wutong/`。

## 运行时覆盖说明

每条 runs 及 tuning.before 必须保存当时数据集的 coverage_notes，格式与导入 manifest 相同；查询失败或未执行也必须保留。导出器读取运行时快照，不能事后从另一个版本的库补填。缺少快照的历史运行不能冒充新版本运行证据，需在支持快照的入口重跑。示例使用 w04-0.3.0。
