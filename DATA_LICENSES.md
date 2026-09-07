# 数据来源、署名与许可

本仓库整理自下列公开数据。来源数据分别遵循其原许可；仓库的公开发布不改变原许可，也不表示原作者认可本项目。

| 文件 | 原始来源与署名 | 数据许可 |
|---|---|---|
| `data/sgsc.jsonl.gz`、`tables/sgsc_*.csv`、`examples/sgsc_*.json` | Australian Government, Department of the Environment and Energy，*Smart-Grid Smart-City Customer Trial Data*。项目由澳大利亚政府和 Ausgrid 牵头的行业联合体共同资助。[官方数据目录](https://www.data.gov.au/data/dataset/smart-grid-smart-city-customer-trial-data) | [CC BY 3.0 Australia](https://creativecommons.org/licenses/by/3.0/au/) |
| `data/iflex.jsonl.gz`、`tables/iflex_*.csv`、`examples/iflex_*.json` | Hofmann, Matthias & Siebenbrunner, Turid. *A rich dataset of hourly residential electricity consumption data and survey answers from the iFlex dynamic pricing experiment*, v2. [Zenodo，10.5281/zenodo.8248802](https://doi.org/10.5281/zenodo.8248802) | [CC BY 4.0 International](https://creativecommons.org/licenses/by/4.0/) |

许可依据于 2026-09-07 从官方目录 API 核对，记录见 `provenance/source_licenses.json`。SGSC 使用数据集及资源层的 CC BY 3.0 Australia 标记，不用网站页脚的一般许可替代数据许可。

## 本次做了哪些整理

EnergyBridge 项目筛选了能关联同户资料、历史用电和活动读数的候选，排除已识别的 SGSC 条件冲突记录。导出保留原清洗批次的输入、实测答案和已有参考估计；SGSC 单表历史增加统一 `energy_kwh` 字段，其值与普通供电原通道相同，双表沿用已核验的逐时段合计。

汇总 CSV 是从这些记录派生的便读表：计算窗口总电量、平均功率和最高区间平均功率，并展开部分问卷字段。已有参考存在时才导出参考总量及差值，未额外拟合基线或构造因果响应。完整观测另用 Gzip 压缩。源数据中已匿名化的户号用于关联同户记录；本仓库不发布本地文件路径、账号凭据或工作区运行日志。

继续分享这些数据时，请保留原始来源、许可链接及以上修改说明。公开不代表可以把本项目派生数据重新署名为原始采集数据。

仓库中的读取和核验脚本供复现本次分析数据包使用；未另外指定软件开源许可。原始数据本身仍适用上表许可。
