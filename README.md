# 家庭负荷模拟 benchmark：SGSC / iFlex

本仓库提供 SGSC 和 iFlex 的家庭负荷预测数据、构造代码及评分工具。每条样本用家庭资料、此前七天用电和当天活动条件，预测同户当天的整户电量序列。当前版本为 **[benchmark v1.0.0](benchmark/v1/README.md)**，采用回顾性条件预测任务。研究说明见 [Notion](https://app.notion.com/p/3d406135328a817f94d9d1918f323c89)。

| 来源 | 有保留样本的家庭 | 保留家庭日 | 隔离家庭日 | 原生全天答案 |
|---|---:|---:|---:|---|
| SGSC | 2,076 | 16,246 | 84 | 48 个半小时 kWh |
| iFlex | 314 | 2,071 | 0 | 24 个小时 kWh |

合计 **2,390 户、18,317 条保留样本**。画像文件仍保留原来全部 2,392 户，供追溯。隔离的 84 条在历史或目标中存在连续至少 24 小时零读数，原因未明，原值完整保存在隔离文件。iFlex 22 户的明确无车回答已统一为汽车和电动车数量为零，影响 149 条样本。

家庭成员、住房、设备和使用习惯按统一字段整理。来源没有记录的内容保留为未知；答案来自整户电表，未提供逐设备运行轨迹。

## 文件入口

初次阅读建议先看 [中文字段说明](sharing/iflex_Exp_1_2020-02-11_字段说明.md)，再对照 [完整单条 JSONL](sharing/iflex_Exp_1_2020-02-11.jsonl)。全量数据可下载 [SGSC](https://raw.githubusercontent.com/Fanmili-5/household-load-simulator-data/benchmark-v1.0.0/benchmark/v1/data/sgsc.jsonl.gz) 和 [iFlex](https://raw.githubusercontent.com/Fanmili-5/household-load-simulator-data/benchmark-v1.0.0/benchmark/v1/data/iflex.jsonl.gz)，均为 Gzip 压缩的 JSONL，一行对应一个家庭日。

- 数据与完整样例：[交付说明](benchmark/v1/README.md)、[SGSC 样例](benchmark/v1/examples/sgsc.json)、[iFlex 样例](benchmark/v1/examples/iflex.json)。
- 修正与隔离：[画像修正](benchmark/v1/provenance/profile_corrections.json)、[隔离索引](benchmark/v1/quarantine/index.csv)、[原读数复核](benchmark/v1/provenance/zero_review.json)。
- 输入依据：[时间和费率证据](benchmark/v1/provenance/input_evidence.json)、[字段覆盖](benchmark/v1/provenance/profile_field_coverage.csv)。
- 格式与评测：[样本 schema](benchmark/v1/schema/sample.schema.json)、[评测协议](benchmark/v1/evaluation/protocol.json)、[固定划分](benchmark/v1/splits/household_holdout.csv)。
- 验证：[清单](benchmark/v1/manifest.json)、[全量验证](benchmark/v1/validation.json)。
- 可选扩展：[iFlex 历史气温与家庭变化复核](extensions/iflex_context_v1/README.md)。气温可作为额外历史输入；事后问卷仅供复核，主版本与划分保持原样。

## 读取与检查

```bash
python3 scripts/verify_benchmark.py
python3 -m unittest discover -s tests -v
```

```python
from scripts.benchmark_io import read_samples
sample = next(read_samples("iflex", split="train"))
```

导出训练分区的 SFT 消息候选，不启动模型：

```bash
python3 scripts/benchmark_io.py --split train --track retrospective_conditional --variant full --output outputs/benchmark_train.jsonl.gz
```

当前有回顾性评测接口；逐户问卷时刻与通知送达时刻未获完整核实，严格实时预测集合为空。SGSC 费率保持未知，活动类型与白天在家字段完全重合；评分按来源和活动类型分别输出，另提供去掉白天在家字段的输入版本。不能用这个分组关系证明居家习惯的独立作用。

## 复现所需的源文件

当前使用 `benchmark/v1/`。根目录的 `data/`、`tables/`、`examples/` 及 `baseline/v1/` 是早期观测或本版构造输入，供复现和追溯；其中的窗口与样例不作为当前训练格式。来源提取过程见 [提取复核](docs/EXTRACTION_AUDIT_20260908.md)。

数据来源和复用条件见 [DATA_LICENSES.md](DATA_LICENSES.md)。
