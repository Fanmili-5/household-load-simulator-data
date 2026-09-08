# 阅读样本与覆盖统计

- [完整单条 JSONL](iflex_Exp_1_2020-02-11.jsonl)：一行一条完整记录，未省略任何字段或数组，与 benchmark v1.0.0 的对应样本一致。
- [中文字段说明](iflex_Exp_1_2020-02-11_字段说明.md)：逐模块解释、未知值含义及 24 小时价格与真实电量对照。
- [实际覆盖统计](profile_coverage.json)：仅统计至少有一条保留样本的 2,390 个不同家庭，区别于归档画像的 2,392 户。

数据格式、划分和评分规则见 [benchmark v1.0.0](../benchmark/v1/README.md)。完整历史和答案不代表完整家庭画像；20 类设备的未知比例由固定目录计算，不能解释为源表丢失率。研究讨论与论文依据放在 Notion。

复算覆盖：

```bash
python3 scripts/summarize_profile_coverage.py
```

样本沿用 iFlex 的 CC BY 4.0 许可与原作者署名，见根目录 [DATA_LICENSES.md](../DATA_LICENSES.md)。本目录不改变已发布的 benchmark 数据。
