# 梧桐书店：从原始导出到可查询数据

梧桐书店有多家门店和线上销售渠道。这份例题包含 2,017 个读者账号及约 2 万条门店销售记录。线上订单在另一平台，这次没有导出，因此查询结果只能代表已导入的门店数据。

## 文件和阅读顺序

1. 先看 `raw/` 的原始导出和 `materials/导出字段手册.md`，核对字段、金额单位、日期及取值。
2. 阅读 `customer/w04/solution.py` 的 profile 入口，查看逐字段统计、异常证据与字典差异。
3. 对照 `materials/cleaning_rules.yaml` 和 `materials/tags.txt`，沿 adapt 入口阅读清洗、映射、隔离和覆盖说明。
4. 查看 `snapshots/complete/artifacts/w04/` 的清洗 CSV、对账报告和 demo_run.json，核对接受记录、隔离记录与原始出处。

`snapshots/start/` 是空白实现，`snapshots/complete/` 是完成实现。两份快照使用相同的原始数据。`source_row` 按 CSV 记录计数，字段内换行不会增加记录序号。

## 重放两份快照

在工程根目录使用已安装依赖的 Python 执行，输出目录必须不存在：

```sh
python examples/w04/wutong/replay.py --snapshot start --output artifacts/wutong-start
python examples/w04/wutong/replay.py --snapshot complete --output artifacts/wutong-complete
python -m unittest discover -s examples/w04/wutong/customer/w04 -p 'test_*.py'
```

起始状态能读取原始数据、导入准备数据，剖析和适配空白入口会明确失败。完成状态会重新剖析、适配，并在两个新查询库中全量导入后对账。

## 运行反例

```sh
python examples/w04/wutong/counterexamples.py --raw examples/w04/wutong/raw --cleaned examples/w04/wutong/snapshots/complete/artifacts/w04/cleaned --output artifacts/wutong-counterexamples
```

默认运行四个反例：少一列后整表被读成 1 列、误删斜杠合法标签、ignore_errors 丢记录、在旧库追加导致订单翻倍。结果保存到输出目录的 results.json。

来源缺口反例需要未导出平台的订单，学员包不提供；默认会说明原因并跳过。获得补充订单文件后，可使用 `--online` 指定该文件，运行全部五项。

本例的数据版本为 `wutong-w04-v1`，读者卡文件保留空表。完整提交格式和数据导入约定见 [W04 产出物契约](../../../contracts/w04/README.md)。
