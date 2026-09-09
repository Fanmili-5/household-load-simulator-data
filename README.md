# 家庭负荷 benchmark：SGSC / iFlex / LIRNEasia

本仓库提供真实家庭的画像、多设备信息、连续用电历史、实测答案、固定划分与评分代码。输入为同户资料、此前七天用电和目标日条件，预测完整一天的区间电量。**2026-09-09 已实际加入 LIRNEasia 数据扩展**。汇报入口：[Notion](https://app.notion.com/p/3d406135328a817f94d9d1918f323c89)；[阶段汇报提纲](docs/REPORT_BRIEF_20260909.md)；[构造参考与完整细节](docs/BENCHMARK_CONSTRUCTION_20260909.md)。

| 来源 | 默认保留家庭 | 默认家庭日 | 隔离家庭日 | 原生全天答案 | 版本与任务 |
|---|---:|---:|---:|---|---|
| SGSC | 2,076 | 16,246 | 84 | 48 个半小时 kWh | 冻结 v1：回顾性活动条件预测 |
| iFlex | 314 | 2,071 | 0 | 24 个小时 kWh | 冻结 v1：实验价格条件预测 |
| **LIRNEasia** | **410** | **6,325** | **335** | **96 个 15 分钟购电 kWh** | **独立扩展：日常次日预测** |

默认保留资源合计 **2,800 户、24,642 个家庭日**，分别按来源使用和评测。原 [benchmark v1.0.0](benchmark/v1/README.md) 的 SGSC/iFlex 2,390 户、18,317 条与原划分保持冻结，不自动混为三来源排行榜。

LIRNEasia 先完整核验得到 **422 户、6,660 个连续窗口**，再沿用连续至少 24 小时精确零读数隔离规则，默认保留 410 户、6,325 条。全部 422 户的原问卷、累计读数摘录和 335 条隔离原记录均保留。问卷早于历史窗口；没有实际调控事件或同意标签。它为真实同户画像与日常负荷的预测补充独立数据。

## 新增 LIRNEasia：下载、读取与复现

- [数据包与全部构造说明](extensions/lirneasia_history_v1/README.md)
- [默认数据 JSONL.gz](extensions/lirneasia_history_v1/data/lirneasia.jsonl.gz) · [完整样例](extensions/lirneasia_history_v1/examples/lirneasia.json) · [家庭划分](extensions/lirneasia_history_v1/splits/household_holdout.csv)
- [隔离原记录](extensions/lirneasia_history_v1/quarantine/lirneasia.jsonl.gz) · [原始来源与哈希](extensions/lirneasia_history_v1/provenance/source_integrity.json) · [全量验证](extensions/lirneasia_history_v1/verification.json)

```bash
python3 scripts/verify_lirneasia_extension.py
python3 scripts/build_lirneasia_extension.py --output outputs/lirneasia_rebuilt
```

```python
import sys
sys.path.insert(0, 'scripts')
from lirneasia_io import read_samples, model_input
sample = next(read_samples('train'))
x = model_input(sample, 'history_profile')
y = sample['output']['energy_kwh']
```

以下为冻结 SGSC/iFlex 主版本的入口与命令。家庭画像中的未知保持未知；整户电表答案不表示逐设备运行轨迹。

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

SGSC/iFlex v1 有回顾性评测接口；逐户问卷时刻与通知送达时刻未获完整核实，严格实时预测集合为空。SGSC 费率保持未知，活动类型与白天在家字段完全重合；评分按来源和活动类型分别输出，另提供去掉白天在家字段的输入版本。不能用这个分组关系证明居家习惯的独立作用。

## 复现所需的源文件

SGSC/iFlex 使用 `benchmark/v1/`，LIRNEasia 使用 `extensions/lirneasia_history_v1/`。根目录的 `data/`、`tables/`、`examples/` 及 `baseline/v1/` 是早期观测或本版构造输入，供复现和追溯；其中的窗口与样例不作为当前训练格式。来源提取过程见 [提取复核](docs/EXTRACTION_AUDIT_20260908.md)。

数据来源和复用条件见 [DATA_LICENSES.md](DATA_LICENSES.md)。
