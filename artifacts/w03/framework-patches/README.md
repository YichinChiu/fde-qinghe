# 本地框架补丁记录

## builder-build-max-tokens（2026-11-05）

- 文件：`platform/fde_product/metrics/builder.py` 第 46 行。原文件备份：`patches/original/builder.py`；差异：`patches/builder-build-max-tokens.diff`。
- 改动：构建调用的输出上限原为写死的 32768；改为可用环境变量 `FDE_W03_BUILD_MAX_TOKENS` 覆盖，**未设置时仍为 32768**，默认行为不变。
- 原因：使用 `gemini-3.8-flash`（OpenAI 兼容端点）时，思考 token 计入总用量但不计入 `completion_tokens`。`artifacts/w03/build-v3`、`build-v4` 均在可见输出 1686／7969 token 时以 `finish_reason=length` 结束（total_tokens 50564，prompt 17800），框架因 `completion_tokens` 未达上限而判为 `MODEL_LENGTH_LIMIT_UNCONFIRMED`，不会进入 65536 的截断重试，无法通过 `FDE_MODEL_MAX_TOKENS` 调整。
- 影响范围：只影响构建时向模型请求的输出上限。生成结果仍经框架原有的来源核对、三项检查与 `load` 时的重新检查；指标库的执行、加载、测试与 `check` 代码均未改动，教师用原版框架加载同一库不受影响。
- 未修补：`dimensions.json` 中多跳实体 `home_store` 的路径映射缺陷（见 `artifacts/w03/framework-issue/README.md`）。它影响查询执行，教师复查用原版框架，因此保留原样并反馈课程方。
