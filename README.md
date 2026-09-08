# 家庭负荷模拟 benchmark：SGSC / iFlex

当前交付为 **[benchmark v1.0.0](benchmark/v1/README.md)**：统一家庭表示、同户七天历史与全天实测答案、质量隔离、固定家庭划分、输入转换及评分代码。当前任务是**给定已记录家庭与活动条件的回顾性整户负荷预测**。论文与研究取舍见 [Notion](https://app.notion.com/p/3d406135328a817f94d9d1918f323c89)。

| 来源 | 有保留样本的家庭 | 保留家庭日 | 隔离家庭日 | 原生全天答案 |
|---|---:|---:|---:|---|
| SGSC | 2,076 | 16,246 | 84 | 48 个半小时 kWh |
| iFlex | 314 | 2,071 | 0 | 24 个小时 kWh |

合计 **2,390 户、18,317 条保留样本**。画像文件仍保留原来全部 2,392 户，供追溯。隔离的 84 条在历史或目标中存在连续至少 24 小时零读数，原因未明，原值完整保存在隔离文件。iFlex 22 户的明确无车回答已统一为汽车和电动车数量为零，影响 149 条样本。

每户采用相同字段框架，未知保持未知。20 类设备是目录容量；不能理解为每户都有完整的 20 类调查。此版不补造设备、作息、费率或电量。

## 信息实际覆盖到什么程度

历史与答案完整，画像覆盖不均。下表按**有保留样本的不同家庭**统计，SGSC 分母为 2,076 户，iFlex 为 314 户；“已知”包含明确没有或数量为零。

| 信息 | SGSC 已知户数 | iFlex 已知户数 |
|---|---:|---:|
| 家庭人数 | 0 / 2,076 | 314 / 314 |
| 自报房型 | 985 / 2,076 | 314 / 314 |
| 来源分类房型（与自报分开） | 2,076 / 2,076 | 0 / 314 |
| 住房面积区间 | 0 / 2,076 | 314 / 314 |
| 冰箱数量 | 2,076 / 2,076 | 0 / 314 |
| 洗衣机、洗碗机持有情况 | 两类均为 0 / 2,076 | 两类均为 0 / 314 |
| 电动车／插混汽车数量（含零） | 0 / 2,076 | 314 / 314 |
| 每户设备有无已知类别的中位数 | 4 / 20 类 | 6 / 20 类 |

20 类设备的有无字段中，未知占比为 SGSC **81.1%**、iFlex **70.3%**。这是固定目录的覆盖程度，包含来源未调查的类别，不是源记录丢失率。空值保留事实边界，但会增加完整 JSON 的输入长度；尚未验证具体模型的上下文预算和预测效果。

本版适合评审现有数据构造及开展整户负荷预测实验；它没有提供完整逐电器运行记录，不能据此称为完整多电器行为评测。数据研究思路见 Notion。

首次阅读可先看 [完整单条 JSONL](sharing/iflex_Exp_1_2020-02-11.jsonl) 和 [中文字段说明](sharing/iflex_Exp_1_2020-02-11_字段说明.md)。[覆盖明细](sharing/profile_coverage.json)由 `python3 scripts/summarize_profile_coverage.py` 复算；这次说明更新没有改动 benchmark v1.0.0 的数据、划分或评分规则。

## 文件入口

- 数据与完整样例：[交付说明](benchmark/v1/README.md)、[SGSC 样例](benchmark/v1/examples/sgsc.json)、[iFlex 样例](benchmark/v1/examples/iflex.json)。
- 修正与隔离：[画像修正](benchmark/v1/provenance/profile_corrections.json)、[隔离索引](benchmark/v1/quarantine/index.csv)、[原读数复核](benchmark/v1/provenance/zero_review.json)。
- 输入依据：[时间和费率证据](benchmark/v1/provenance/input_evidence.json)、[字段覆盖](benchmark/v1/provenance/profile_field_coverage.csv)。
- 格式与评测：[样本 schema](benchmark/v1/schema/sample.schema.json)、[评测协议](benchmark/v1/evaluation/protocol.json)、[固定划分](benchmark/v1/splits/household_holdout.csv)。
- 验证：[清单](benchmark/v1/manifest.json)、[全量验证](benchmark/v1/validation.json)。

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

## 已保留的原观测与旧示例

根目录 `data/`、`tables/`、`examples/` 保存此前的观测版本和部分字段演示，供追溯及复现。旧 SGSC 的 16,342 条记录只覆盖活动窗口；首个全天观测版本在 `baseline/v1/`；当前 benchmark 在 `benchmark/v1/`。两者不能混计样本数。旧字段说明见 [FIELDS](docs/FIELDS.md)，来源提取过程见 [提取复核](docs/EXTRACTION_AUDIT_20260908.md)。

SGSC 按登记表计合计家庭电量：单表使用普通供电，两表逐点加上受控负荷。原先排除的 258 条条件冲突记录仍未纳入；旧观测批次曾单列 1,526 条缺辅助产品佐证的记录，详见旧观测的 [剔除表](tables/sgsc_exclusions.csv)与元数据。

数据来源和复用条件见 [DATA_LICENSES.md](DATA_LICENSES.md)。
