# 数据来源、署名与许可

本仓库整理自下列公开数据。来源数据分别遵循其原许可；仓库的公开发布不改变原许可，也不表示原作者认可本项目。

| 文件 | 原始来源与署名 | 数据许可 |
|---|---|---|
| `data/sgsc.jsonl.gz`、`tables/sgsc_*.csv`、`examples/sgsc_*.json` | Australian Government, Department of the Environment and Energy，*Smart-Grid Smart-City Customer Trial Data*。项目由澳大利亚政府和 Ausgrid 牵头的行业联合体共同资助。[官方数据目录](https://www.data.gov.au/data/dataset/smart-grid-smart-city-customer-trial-data) | [CC BY 3.0 Australia](https://creativecommons.org/licenses/by/3.0/au/) |
| `data/iflex.jsonl.gz`、`tables/iflex_*.csv`、`examples/iflex_*.json`、`provenance/iflex_profile_*` | Hofmann, Matthias & Siebenbrunner, Turid. *A rich dataset of hourly residential electricity consumption data and survey answers from the iFlex dynamic pricing experiment*, v2. [Zenodo，10.5281/zenodo.8248802](https://doi.org/10.5281/zenodo.8248802) | [CC BY 4.0 International](https://creativecommons.org/licenses/by/4.0/) |

许可依据于 2026-09-07 从官方目录 API 核对，记录见 `provenance/source_licenses.json`。SGSC 使用数据集及资源层的 CC BY 3.0 Australia 标记，不用网站页脚的一般许可替代数据许可。

## 本次做了哪些整理

本研究筛选了能关联同户资料、历史用电和活动读数的候选，排除已识别的 SGSC 条件冲突记录。导出保留原清洗批次的输入、实测答案和已有参考估计；SGSC 单表历史增加统一 `energy_kwh` 字段，其值与普通供电原通道相同，双表沿用已核验的逐时段合计。

汇总 CSV 是从这些记录派生的便读表：计算窗口总电量、平均功率和最高区间平均功率，并展开部分问卷字段。已有参考存在时才导出参考总量及差值，未额外拟合基线或构造因果响应。完整观测另用 Gzip 压缩。源数据中已匿名化的户号用于关联同户记录；本仓库不发布本地文件路径、账号凭据或工作区运行日志。

baseline v1.0.0 另外将这两份来源映射为统一家庭字段，从同户原始读数重建完整七天历史与全天答案，排除 12 个缺少完整窗口的 SGSC 候选。`baseline/v1/data/`、`baseline/v1/profiles/`、`baseline/v1/examples/` 及其字段映射继续分别适用上述 SGSC 或 iFlex 数据许可；未补造设备、行为或读数。

继续分享这些数据时，请保留原始来源、许可链接及以上修改说明。公开不代表可以把本项目派生数据重新署名为原始采集数据。

2026-09-08 又按同户原始家庭表和 Survey 1 扩展了家庭与设备画像，保留完整源回答，增加字段来源、缺失与异常状态，并对不一致的人口分组置空而不猜测修正。完整修改说明见 `docs/PROFILE_UPDATE_20260908.md`；这些派生画像及家庭表仍适用各自来源数据的许可。

仓库中的读取和核验脚本供复现本次分析数据包使用；未另外指定软件开源许可。原始数据本身仍适用上表许可。
