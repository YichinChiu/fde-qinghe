# W04 运营 Agent 与数据接入工具

工程版本：w04-0.1.0；包修订：e15-c4。

先读外层材料包的 00_使用说明.md 和 05_作业任务书.md。安装沿用 [W03 使用与安装](docs/w03/README.md)的环境准备，模型配置见 [模型说明](docs/model-configuration.md)。本周在新的解压目录新建虚拟环境，安装 requirements-w03.txt，运行 tools/w03.py doctor；W03 说明中的旧周作业步骤不代替本周任务书。

本周从 [W04 客户代码入口](customer/w04/README.md)、[契约和命令](contracts/w04/README.md)、[梧桐书店例题](examples/w04/wutong/README.md)开始。先重放起始与完成快照并运行反例。四份交付文档的空白模板在 templates/w04/documents/，在工程根目录执行 `tools/w04.py init --workspace .` 补齐模板，运行目录与命令见客户代码入口。

W01～W03 工具与独立例题继续可用；本周青禾数据在外层数据包中。已有 W03 交付或 checkpoint 原样保留，在工作副本上承接；将 W03 业务模型复制为 docs/w04/business_model.md，按本周证据核对和修订，在 model_changes.md 记录依据，并与指标库核对一致。W04 截止后释放的 checkpoint 不在本包中。
