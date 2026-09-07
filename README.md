# 家庭模拟数据 baseline：SGSC / iFlex

当前交付为 **[baseline v1.0.0](baseline/v1/README.md)**：统一家庭字段、同户七天历史、当天条件和完整日实测答案。研究思路、论文依据与设计取舍放在 [Notion](https://app.notion.com/p/3d406135328a817f94d9d1918f323c89)。

| 来源 | 家庭数 | 完整家庭日 | 历史点数 | 全天答案 |
|---|---:|---:|---:|---|
| SGSC（澳大利亚） | 2,078 | 16,330 | 336 | 48 个半小时 kWh |
| iFlex（挪威） | 314 | 2,071 | 168 | 24 个小时 kWh |

每条样本保留同一户的家庭成员、住房、20 类设备的统一字段、能源服务、使用习惯、偏好和逐车资料。设备目录统一，已知值按真实记录填入；没有记录的信息保持未知。20 类目录不等于每户都有这些设备或来源调查了全部类别。

SGSC 另有 12 条原活动记录无法组成完整窗口，已列明原因。两份数据合计 **2,392 户、18,401 条完整日样本**。数据构造已完成，逐户画像采集与通知送达时刻仍有待核实项，故未标为正式训练发布；没有运行模型训练。

## 直接查看

- 完整样例：[SGSC](baseline/v1/examples/sgsc.json) · [iFlex](baseline/v1/examples/iflex.json)。两例都使用完整语义画像。
- 全部家庭日：[SGSC](baseline/v1/data/sgsc.jsonl.gz) · [iFlex](baseline/v1/data/iflex.jsonl.gz)。每行包含完整输入和实测答案。
- 每户画像及来源：[SGSC](baseline/v1/profiles/sgsc.jsonl.gz) · [iFlex](baseline/v1/profiles/iflex.jsonl.gz)。原回答和质量标记保存在这里。
- 格式定义：[家庭 schema](baseline/v1/schema/profile.schema.json) · [样本 schema](baseline/v1/schema/sample.schema.json)。
- 核对信息是否遗漏：[142 个源字段的去向](baseline/v1/provenance/source_field_mapping.csv) · [实际字段覆盖](baseline/v1/provenance/profile_field_coverage.csv)。
- 验收：[版本清单](baseline/v1/manifest.json) · [验证结果](baseline/v1/validation.json) · [窗口剔除表](baseline/v1/provenance/window_exclusions.json)。
- 读取、转换规则、按家庭划分及重建命令：[交付说明](baseline/v1/README.md)。

## 读取与检查

```bash
git clone https://github.com/Fanmili-5/household-load-simulator-data.git
cd household-load-simulator-data
python3 scripts/read_baseline.py --source iflex
python3 scripts/verify_baseline.py
```

在仓库中使用 Python：

```python
from scripts.read_baseline import read_samples

sample = next(read_samples("sgsc", split="train"))
profile = sample["input"]["profile"]
history = sample["input"]["history"]
context = sample["input"]["context"]
answer = sample["output"]["energy_kwh"]
```

将固定训练分区转换成消息格式，不会运行训练：

```bash
python3 scripts/export_baseline_sft.py --split train --output outputs/baseline_train.jsonl.gz
```

## 已保留的原观测与旧示例

根目录 `data/`、`tables/`、`examples/` 保存此前的观测版本和部分字段演示，供追溯及复现。旧 SGSC 的 16,342 条记录只覆盖活动窗口；新的全天 baseline 在 `baseline/v1/`。两者不能混计样本数。旧字段说明见 [FIELDS](docs/FIELDS.md)，来源提取过程见 [提取复核](docs/EXTRACTION_AUDIT_20260908.md)。

SGSC 按登记表计合计家庭电量：单表使用普通供电，两表逐点加上受控负荷。原先排除的 258 条条件冲突记录仍未纳入；1,526 条缺辅助产品佐证的记录保留原证据状态，详见旧观测的 [剔除表](tables/sgsc_exclusions.csv)与元数据。

数据来源和复用条件见 [DATA_LICENSES.md](DATA_LICENSES.md)。
