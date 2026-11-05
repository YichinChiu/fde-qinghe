# 指标核定与未决项

定稿库：`artifacts/w03/library`，由 `artifacts/w03/build-v8` 经 `merge` 生成（38 项全部定义，三项检查通过）；上一版定稿库（来自 `build-v2`）改名保留为 `artifacts/w03/library-v1`。逐项定义、单位、来源引文与查询限制见 `artifacts/w03/library/catalog.json` 与 `metrics.yml`，派生计算见 `ranked_orders.sql`、`member_monthly_summary.sql`。两版业务定义相同，v8 只改了 catalog constraints 的组织方式（见“构建迭代记录”）。下文不重抄定义，只记采用依据和核定判断。

构建输入：`docs/w03/business_model.md`（W03 第 2 轮 apply 版）、`materials/w03/00–08`、小样本 `qinghe-w03-20260923-small`。构建方法：`customer/w03/build-metrics/SKILL.md`（构建时快照见各构建目录 `skill_used.md`）。

## 采用依据

- **订单数族**（`order_count`、`paid_order_count`、`valid_order_count`、`cancelled_order_count`、`refund_order_count`、`partial_refund_order_count`、`full_refund_order_count`）：采用 `01_订单日报说明.md` 各节定义；“有效”以 `02_财务邮件.md`“有效订单是 paid 状态且实付大于累计退款”为准，与 01 的“实付金额减退款金额大于零”等价，不构成冲突。统计时间为下单日期 `ordered_at`。核对过 measure：部分退款为“退款大于零且小于实付”，全额退款为“实付大于零且退款等于实付”，与原文比较符一致。
- **金额族**（`payment_cents`、`refund_cents`、`net_sales_cents`、`gross_cents`、`discount_cents`）：采用 01 原文；退款按原订单下单日期归属（01、02 一致），数据字典 `refund_cents` 为截至快照的累计退款，没有退款发生日，因此只能按原订单日期统计；优惠金额为原价减实付，退款不冲减。单位整数分，展示元须换算。
- **会员与门店去重族**（`buyer_count`、`refund_buyer_count`、`selling_store_count`）：采用 01；按 CRM 账户 `member_id`、订单门店 `store_id` 去重，不做跨系统自然人去重（数据字典；老周 MSG-03567）。
- **件数**（`valid_order_items`）：采用 01“有效订单中的原始购买件数合计；…此项不是净商品销量”。
- **比率族**（`avg_order_value`、`avg_buyer_value`、`purchase_frequency`、`refund_amount_rate`、`cancel_rate`、`refund_order_rate`、`discount_rate`、`items_per_order`）：采用 `02_财务邮件.md` 的分子分母；零分母未定义（null，不填 0）；单位分别为 `cents_per_order`、`cents_per_member`、`orders_per_member`、`ratio`（四项）、`items_per_order`。比率为原始比率，不是百分数。
- **注册会员**（`new_member_count`）：采用 `03_会员运营周报.md`；按 `registered_at` 归属。按等级分组时用账户**当前登记等级**，回答注明“不是注册当时的等级”（小林 MSG-03556 同意本期用法）；`tier` 是否快照老周不掌握（MSG-03569），列为数据限制。
- **观测期首购族**（`first_buyer_count`、`first_order_sales_cents`、`first_order_count`、`repeat_order_count`）：采用 03“先用全覆盖历史确定首次，再按窗口筛选”“相同日期按订单号排序”。派生模型 `ranked_orders` 在全部覆盖期内对有效订单按 `(ordered_at, order_id)` 排序，查询窗口只在其后筛选。不代表终身首购。
- **月内复购族**（`monthly_buyer_count`、`monthly_repeat_buyer_count`、`monthly_repeat_rate`）：采用 03，复购率分母为同月有效购买账户（周报已说明从“全部注册会员”调整而来）。派生模型 `monthly_buyer_summary` 一行一个“账户×月”；`full_month_only=true`，多月按月分别列出。
- **月末付费会员族**（`monthly_paid_*` 六项）：
  - 统计选择采用 `04_本期统计确认邮件.md`：按自然月最后一天判资格，先选月末有资格账户，再统计其当月全渠道、全门店有效订单；不要求订单当天已有资格；只支持完整自然月、全渠道全门店，`full_month_only=true`。王经理 MSG-03545 复述一致。
  - 卡种范围：悦享年卡、家庭季卡；联名卡、体验卡不算；等级和付款金额不代替卡种与有效状态；多卡只算一个账户（小林 MSG-03548、03558；陈姐 MSG-03579）。**状态：运营口头答复，待书面确认**（王经理 MSG-03539 要求书面确认）。
  - `valid_from` 落在月底当天：“月末才生效、但当月此前有购买的账户，才纳入当月有效购买”（小林 MSG-03554、03556）。**状态：运营口头答复，待书面确认。**
  - `valid_until`、`ended_at` 落在月底当天：**本期暂定口径**——当天不算有效。依据为门店实际做法（陈姐 MSG-03579、03581、03583）；运营未确认，等老周核对系统记录后对齐（小林 MSG-03586）；FDE 2026-11-05 决定在确认前按此计算。六项 catalog `constraints` 均已写明“本期暂定口径”与待确认方。

## 冲突、未决与不支持

| 事项 | 影响 | 状态 | 下一步 |
| --- | --- | --- | --- |
| `valid_until`／`ended_at` 月底当天是否有效 | 6 项付费会员月报。小样本 2026-08：M00010（valid_until 08-31）、M00005、M00011（ended_at 08-31）在暂定口径下不计；若改为当天有效，购买人数 +3、复购人数 +2 | 本期暂定口径；运营未确认，老周核对中，时间未定 | 收到运营与 IT 结论后更新业务模型，用新目录重建、重新加载、回归全部用例 |
| `valid_from` 等于月底且当月唯一一笔购买就在月底当天 | 付费会员月报。小样本 M00007（valid_from 08-31，唯一有效订单 08-31）按小林原话“当月此前有购买”字面解读不计；M00013（另有 08-05 订单）计入 | FDE 对原话的字面解读，小林未就“当天购买”单独作答 | 在书面确认中请运营写明“此前”是否包含生效当天；列入 SOW 待确认 |
| 运营书面确认由谁出具 | 卡种范围、多卡、valid_from 口径能否成为约定依据 | 小林 MSG-03558 说可由她出，MSG-03586 改为“不是我一个人能出的” | 请小林说明出具主体与流程；SOW 列为客户方依赖 |
| 卡表历史覆盖 | 付费会员月报在 2026-01 之前各月（小样本卡均自 2026-01-01 起） | 老周不掌握（MSG-03565）；本期按测试卡表计算，结果为 0 时 constraints 要求说明不能解读为没有付费会员 | 老周与运营核对后决定是否限制可查询月份 |
| 小程序订单 `store_id` 含义 | `selling_store_count` 及按成交门店分组、筛选 | 老周不掌握（MSG-03567）；陈姐要求核实前不能当作门店归属、本期统计不改变考核（MSG-03574）。数据字典定义 `store_id` 为“订单成交门店 ID”，`01_订单日报说明.md` 定义成交门店数为“订单归属门店数”。**FDE 决定**：按字典与日报定义计算（含小程序订单），每项订单指标 constraints 注明“小程序订单门店编号在 IT 核实前不能当作门店归属”“本期统计不改变现有门店考核”，并可按订单渠道筛选分开看 | 老周核实后若含义不是成交门店，改为按渠道限制门店拆分并重建 |
| `tier` 是否快照 | 注册会员按等级分组、按等级筛选 | 老周不掌握；本期按当前登记等级，回答注明 | 无需重建，仅更新说明 |
| 按条件筛选会员（圈选） | 不在 38 项内 | **本期不支持**（王经理 MSG-03541；SOW 列为后续阶段） | 后续阶段以书面范围确认为准 |
| 付费会员月报按门店／渠道拆分、非整月查询 | 6 项付费会员月报 | **本期不支持**（04 邮件），查询返回 unsupported | 无 |
| 覆盖期外（2024-09-01 之前、2026-09-01 及以后） | 全部指标 | 不支持，返回 unsupported，不当作 0 | 无 |

## 解释人工核查

依据：`artifacts/w03/test-small-v2/metric_test_report.json` 中各用例 `actual.answer`，对照 `catalog.json` 的 constraints 与本文件“采用依据”。

| 用例 | 客户是否正确 | 时间、筛选、口径说得对吗 | 有没有把已知说成未知 | 结论 |
| --- | --- | --- | --- | --- |
| aug-orders-cancel、aug-paid-valid、aug-refund-orders、aug-payment-refund、aug-net-sales、aug-gross-discount | 是（青禾） | 是。说明了按原下单日期归属、取消单与全退的处理；金额换算为元、比率显示为百分数，与 rows 中的分和原始比率一致 | 否 | 通过 |
| aug-buyers、aug-items、aug-averages、syn-aug-valid-orders、syn-aug-net-sales | 是 | 是。说明以 CRM 账户为单位、不做跨系统自然人去重；件数“不扣减退货件数” | 否 | 通过 |
| jul-new-members-by-tier、all-new-members-by-home-store | 是 | 是。注明“按当前登记等级”“不等于自然人数” | 否 | 通过 |
| aug-first-purchase、aug-repeat-orders、jul-first-purchase | 是 | 是。注明“基于测试覆盖期历史”“不代表终身首购” | 否 | 通过 |
| aug-monthly-repeat、jul-aug-monthly-buyers-by-month | 是 | 是。注明整月、全门店口径，按月分别列出、跨月不可相加 | 否 | 通过 |
| mar-2025-zero-denominator | 是 | 是。净销售额 0.00 元；有效订单均额“分母为零，未定义”，未说成 0 | 否 | 通过 |
| aug-valid-orders-by-channel、aug-buyers-region-store-channel、aug-net-sales-gold-tier、aug-net-sales-by-home-region | 是 | 是。渠道、筛选和归属地区角色说明正确 | 否 | 通过 |
| aug-net-sales-by-store、aug-selling-stores | 是 | **不完整**：数值与成交门店口径正确，但没有说明 constraints 中“小程序订单门店编号在 IT 核实前不能当作门店归属、本期统计不改变现有门店考核”（陈姐 MSG-03574 要求注明） | 否 | 要修 |
| aug-paid-buyers-orders-sales | 是 | **部分不准确**：写成“暂定包含悦享年卡与家庭季卡”，把“待书面确认”的卡种范围说成暂定；端点暂定口径说明正确 | 否 | 要修 |
| aug-paid-repeat-avg、jul-paid-buyers | 是 | **不完整**：说明了卡种范围，但没有提端点为本期暂定口径、待运营与 IT 确认；jul-paid-buyers 未说明卡种范围 | 否 | 要修 |
| clarify-no-period、unsupported-* | — | 状态正确（澄清、越界、非整月、按门店拆分付费月报均未算出数字） | 否 | 通过 |

第 2 轮（`test-small-v2`，库 v1）发现的“要修”项，原因判断：constraints 已在 catalog 中，解释调用（`product/w03_answer_prompt.txt`）会收到这些定义，但回答选择性省略。下一轮在 Skill 第四段要求把“回答必须说明”的限制写成每个指标 constraints 的第一条，并在 description 中重复关键限制，重新生成后复核；数值判定不受影响。已按此修订 Skill 并重建为 `build-v8`，第 3 轮复核结果见下表。

第 3 轮（`artifacts/w03/test-small-v3`，库 v8）复核：

| 用例 | 客户是否正确 | 时间、筛选、口径说得对吗 | 有没有把已知说成未知 | 结论 |
| --- | --- | --- | --- | --- |
| aug-net-sales-by-store、aug-selling-stores | 是 | 是。说明了“小程序订单门店编号含义待 IT 核实，核实前不能当作门店归属，不改变现有门店考核” | 否 | 通过 |
| aug-paid-buyers-orders-sales、aug-paid-repeat-avg、jul-paid-buyers | 是 | 是。分开说明卡种与多卡规则“运营口头答复待书面确认”、月末端点“本期暂定口径，待小林与老周核对”、2026-01 前卡表历史覆盖未核实 | 否 | 通过 |
| aug-net-sales（未分组） | 是 | 是。未添加与本次查询无关的门店说明（条件式 constraints 生效） | 否 | 通过 |
| jul-new-members-by-tier | 是 | 是。注明按当前登记等级、非注册当时等级 | 否 | 通过 |

其余用例的回答与第 2 轮同类，抽查未发现退化。

## 测试与回归记录

环境：Windows 11，Python 3.11.12（`.venv`），模型 `gemini-3.8-flash`（Google OpenAI 兼容端点），`FDE_MODEL_TIMEOUT=180`。判定程序 `customer/w03/judge.py`；期望由独立审核程序 `customer/w03/audit.py` 逐记录计算、`customer/w03/make_tests.py` 生成，测试用例意图与“要抓什么错误”见 `customer/w03/test_specs.json`。审核程序先用 2026-08 付费会员手算校准（购买人数 5、复购人数 4，逐账户核对卡种和端点），一致后再生成期望。

| 轮次 | 报告目录 | 失败现象 | 错误来源 | 改了什么 | 回归结果 |
| --- | --- | --- | --- | --- | --- |
| 第 1 轮 | `artifacts/w03/test-small-v1` | 31/32；`aug-net-sales-by-home-store`（按会员归属门店编号分组）返回 `NATIVE_QUERY_FAILED`，意图正确 | 产品（框架）：`dimensions.json` 把订单类指标的 `home_store` 映射为单跳名称，MetricFlow 需要 `member__home_store`；课程自带梧桐库同样复现。证据与分析见 `artifacts/w03/framework-issue/README.md` | 未改期望、未改业务设计绕过；原用例另存 `customer/w03/tests-framework-issue.json` 待框架修复后重跑；主测试集改用“按会员归属地区”（`home_store__region`）检查门店角色区分 | 见第 2 轮 |
| 第 2 轮 | `artifacts/w03/test-small-v2` | 32/32 通过（28 条 ok 覆盖全部 38 项，4 条澄清／越界）；单条耗时 5.9–27.8 秒 | — | — | 全部通过；解释人工核查发现 5 条“要修”，见上节 |
| 第 3 轮 | `artifacts/w03/test-small-v3` | 32/32 通过（库 v8，项目 `.runtime/qinghe-small-v2`）；单条耗时见报告 `actual.elapsed_seconds` | — | 库由 build-v2 换为 build-v8（Skill 第四段新增“回答须说明”规则），重新加载并回归全部用例 | 全部通过；第 2 轮 5 条解释“要修”复核通过。**提交选定报告** |
| 规模第 1 轮 | `artifacts/w03/test-large-v1` | 18/18 通过（库 v8，项目 `.runtime/qinghe-large-v1`，数据 `qinghe-w03-20260923` large：3 万账户、30 万订单、24 店、38,891 张卡）。期望由 `customer/w03/audit.py` 按规模 CSV 逐记录计算（约 20 秒），`customer/w03/tests-large.json`；覆盖订单数族、金额、按成交／归属地区和渠道分组、首购与后续订单、月内复购（含 6–8 月按月）、付费会员月报（含 2025-10～12 按月，规模卡表有 2024-09 起历史）、注册会员按等级、覆盖期外；同义问法 3 组 | — | — | 全部通过。加载耗时约 14.6 秒；原生查询 0.03–0.17 秒／条；含两次模型调用的端到端耗时 13.5–37.8 秒／条 |

错误注入：`artifacts/w03/judge-checks/`（`summary.json` 汇总，每份注入一个文件），基准为第 2 轮真实结果的深拷贝，每份只改一处，均为合成数据。9 类必做注入全部被拒：错指标（01）、错日期（02）、错筛选（03）、错分组／漏组（04a、04b）、元分混淆（05）、比例误作百分数（06）、null 改零（07）、篡改数值（08）、error 伪装成 ok（09a 保留正确行改 error；09b 取第 1 轮真实失败结果改为 ok）。另补：重复组、错数据版本、门店角色互换、布尔值、数字字符串、比率超出容差、多出单位、10 亿对 10 亿零 1，均被拒；原始结果、只改行序、只改列序、整数写成浮点、容差内比率均通过。

错误注入使用的是第 2 轮（库 v1）的真实结果；判定程序 `judge.py` 此后未改，库换版不影响判定逻辑本身的自检结论。

## 构建迭代记录

| 构建目录 | Skill 改动 | 结果 | 原因与处理 |
| --- | --- | --- | --- |
| `build-try1`～`try3` | 初版六段；逐次加强引文规则 | `SOURCE_QUOTE_NOT_EXACT` | 模型引用业务模型时去掉 Markdown 粗体符号。第二段改为“凡所在行出现 `**` 或反引号的句子一律不选作 quote，每条不超过 30 字” |
| `build-try4` | 同上 | 4 项试跑通过 | — |
| `build-v1` | 同上 | 32 定义、6 未决，检查通过 | 业务模型第 1 轮中月底端点未决，6 项付费会员月报按第五段第 2 条列为未决，没有自行补比较符——验证了缺事实时的行为 |
| `build-v2` | 第一段新增“本期暂定口径”使用规则 | 38 定义，检查通过；曾为定稿库 v1 | 业务模型第 2 轮写入门店实际做法与 FDE 暂定口径 |
| `build-v3`、`build-v4` | 第四段新增“回答须说明”规则（含 description 重复） | `MODEL_LENGTH_LIMIT_UNCONFIRMED` | Gemini 思考 token 耗尽 32768 上限但不计入 completion_tokens，框架无法确认截断。删去 description 重复要求 |
| `build-v5` | 同上（删重复） | `MODEL_NETWORK_ERROR` | 网络中断 |
| `build-v6` | 同上；本地补丁允许构建上限 65536 | `MODEL_TIMEOUT`（240 秒） | 思考更长导致超时；`w03.py` 超时上限 240 不可调 |
| `build-v7` | 同上；本地补丁加 `reasoning_effort=low` | `SOURCE_QUOTE_NOT_EXACT`（4 条） | 低推理强度下又引用了含 `**` 的句子 |
| `build-v8` | 同上；`reasoning_effort=medium` | 38 定义，检查通过；**现定稿库** | — |

框架本地补丁见 `patches/README.md`（提交副本：`artifacts/w03/framework-patches/`）：构建输出上限可由 `FDE_W03_BUILD_MAX_TOKENS` 覆盖（默认仍 32768）；仅在设置 `FDE_MODEL_REASONING_EFFORT` 时向请求加入 `reasoning_effort`。两项都只影响构建调用，库的检查、加载、查询、测试与 `check` 代码未改。
