# Household load benchmark

真实家庭的画像、设备资料和连续用电记录。每条 JSONL 对应一个家庭日：以同户资料、此前七天的用电和目标日条件为输入，预测次日各时段的实测电量。

| 数据集 | 默认家庭数 | 默认家庭日 | 隔离家庭日 | 历史 → 答案 | 数据入口 |
|---|---:|---:|---:|---|---|
| SGSC | 2,076 | 16,246 | 84 | 336 → 48 个半小时 kWh | [冻结 v1](benchmark/v1/README.md) |
| iFlex | 314 | 2,071 | 0 | 168 → 24 个小时 kWh | [冻结 v1](benchmark/v1/README.md) |
| LIRNEasia | 410 | 6,325 | 335 | 672 → 96 个 15 分钟购电 kWh | [独立扩展](extensions/lirneasia_history_v1/README.md) |

合计 2,800 户、24,642 个家庭日，按来源分别评测。SGSC/iFlex 的 `benchmark-v1.0.0` 数据、划分与协议保持冻结；LIRNEasia 使用独立的家庭划分。

## 读取数据

```python
import sys
sys.path.insert(0, 'scripts')
from benchmark_io import read_samples
sample = next(read_samples('iflex', split='train'))
x = sample['input']
y = sample['output']['energy_kwh']

from lirneasia_io import read_samples as read_lirneasia
sample = next(read_lirneasia('train'))
```

`input.profile` 保存家庭与设备信息，`input.history` 保存连续七天的区间电量，`input.context` 保存目标时段及来源支持的条件。`output.energy_kwh` 是实测答案。未知值保留为 `null`；`metadata` 用于追溯与筛选，不应整体送入模型。

- 下载：[SGSC](benchmark/v1/data/sgsc.jsonl.gz)、[iFlex](benchmark/v1/data/iflex.jsonl.gz)、[LIRNEasia](extensions/lirneasia_history_v1/data/lirneasia.jsonl.gz)。
- 理解样本：[中文字段说明](sharing/iflex_Exp_1_2020-02-11_字段说明.md)、[三个实测样本与曲线](examples/measured/README.md)、[样本 schema](benchmark/v1/schema/sample.schema.json)。
- 构造与筛选：[数据构造](docs/DATA_CONSTRUCTION.md)、[提取核验](docs/EXTRACTION_AUDIT_20260908.md)、[发布数据统计](provenance/dataset_statistics.json)。
- 评测：[SGSC/iFlex 协议](benchmark/v1/evaluation/protocol.json)、[LIRNEasia 协议](extensions/lirneasia_history_v1/evaluation/protocol.json)。
- 可选输入：[iFlex 历史气温扩展](extensions/iflex_context_v1/README.md)。事后问卷保留在复核文件中。
- 已核验的相似户：[SGSC 两条源记录一致的家庭曲线](analysis/sgsc_matching_households/README.md)。
- 已完成分析：[训练分区的家庭曲线与历史基线](analysis/train_curves/README.md)。

## 校验与复现

```bash
python3 scripts/verify_benchmark.py
python3 scripts/verify_lirneasia_extension.py
python3 scripts/summarize_benchmark.py --output outputs/dataset_statistics.json
python3 -m unittest discover -s tests -v
```

各数据包的 README 提供完整重建命令。原始来源摘录、哈希、隔离记录及家庭划分随包保留。

SGSC 包含活动类型和时段，无法核实的数值费率留空；iFlex 包含实验奖励价格；LIRNEasia 是无调控事件标签的日常购电预测。SGSC/iFlex 当前协议为回顾性条件预测，逐户问卷及通知时间尚不足以建立严格实时预测集合。整户电量没有逐设备运行轨迹或新策略执行后的反事实答案。

根目录 `data/`、`tables/` 及 `baseline/v1/` 保存构造输入和早期版本，供复现追溯。数据来源与复用条件见 [DATA_LICENSES.md](DATA_LICENSES.md)。
