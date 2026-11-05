# 框架问题记录：多跳实体维度的路径映射

发现于 2026-11-05，小样本测试第 1 轮 `artifacts/w03/test-small-v1`，用例 `aug-net-sales-by-home-store`。

## 现象

问题“青禾 2026 年 8 月净销售额按会员归属门店编号分别是多少？”，Agent 理解出的意图正确（`group_by: ["home_store"]`），查询返回 `status: error`、`code: NATIVE_QUERY_FAILED`，MetricFlow 报 “does not match any of the available group-by-items for SimpleMetric('net_sales_cents')”，建议项中有 `member__home_store`。证据：`qinghe-home_store-trace/`。

## 最小复现（不经过大模型，直接调用标准查询）

| 项目 | 意图 | 结果 |
| --- | --- | --- |
| 课程自带梧桐库 `.runtime/wutong-v1`（`examples/w03/library`） | `wutong-home_store-intent.json`：`net_receipts_cents` 按 `home_store` | `NATIVE_QUERY_FAILED`，见 `wutong-home_store-repro/result.json` |
| 青禾定稿库 `.runtime/qinghe-small-v1` | `qinghe-home_store__region-intent.json`：`net_sales_cents` 按 `home_store__region` | `ok`，见 `qinghe-home_store__region-ok/result.json` |

命令：`tools/w03.py query --project <项目> --input <intent.json> --output <目录>`。

## 原因判断

`platform/fde_product/metrics/validation.py` 生成 `dimensions.json` 的 `per_metric` 映射时，若 `list_group_bys` 返回的名字里恰好有与目标 ID 相同的 `home_store`，就直接映射为 `home_store`（第 106 行 `if key in names: resolved[key] = key`）；但对订单类指标，归属门店实体需要经会员两跳，MetricFlow 实际可查询的名字是 `member__home_store`。同一张映射里 `home_store__region` 正确映射为 `member__home_store__region`，所以只有实体本身的多跳路径受影响。梧桐样例库同样复现，与青禾构建方法无关。

## 处理

- 按 `docs/w03/skill-guide.md` 第 7.2 节，不改业务模型设计绕过框架故障，保留证据反馈课程方。
- 原用例原样另存于 `customer/w03/test_specs_framework_issue.json`，期望未改。
- 主测试集改用“按会员归属地区”（`home_store__region`）检查成交与归属两种门店角色的区分，该路径映射正确。
- 待课程方修复后，用新加载目录重跑原用例。
