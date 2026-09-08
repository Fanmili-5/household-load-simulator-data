# iFlex 历史气温与家庭变化复核

本扩展与现有 iFlex 的 **314 户、2,071 个家庭日**按 ID 对应。主数据仍使用 `benchmark/v1/`，家庭划分和全天答案沿用原版。

## 历史气温怎么使用

`inputs/history_weather.jsonl.gz` 每行对应一个原样本，包含此前七天的 168 个小时气温。时间范围与该样本的 `input.history` 完全相同，末端不含预测日。

气温来自家庭所在地区的气象站，单位为 °C；同地区家庭共享天气观测。它不能当作室内温度或家庭独立传感器读数。没有目标日实测天气，也没有用缺失值填补产生的天气。

```python
import gzip
import json
from scripts.benchmark_io import read_samples

with gzip.open("extensions/iflex_context_v1/inputs/history_weather.jsonl.gz", "rt") as f:
    weather = {row["sample_id"]: row["history_weather"]
               for row in map(json.loads, f)}

sample = next(read_samples("iflex", split="train"))
model_input = {**sample["input"], "history_weather": weather[sample["sample_id"]]}
target = sample["output"]
```

完整扩展样例见 [example.json](example.json)。使用这项输入时，应把实验命名为“iFlex + 历史气温”，并在相同家庭划分上与原输入比较；不要与原 v1 的 `full` 输入成绩混记。SGSC 没有本次扩展，未给它补造气温。

小时观测的日期早于预测时点，但气象数据的实际发布时间与延迟未核实。因此扩展仍用于回顾性预测，没有改变原版严格实时预测集合为空的状态。

## 家庭变化复核怎么使用

`review/household_changes.jsonl` 每户一行，仅供事后复核，不能加入上面的 `model_input`。

Survey 2 在 2020 年 5—6 月填写，询问同年 2 月是否发生可能影响用电的家庭变化。原有 314 户中，244 户有第二轮回答，70 户未匹配到回答。**24 户明确选择了变化详情**，包括设备、人数、住房改善或居家情况；多项选择可以重叠。

这 24 户对应 86 个 2 月样本及 76 个 3 月样本。记录将两个月分别列出，因为问卷没有给出变化日期，也不能确定变化是否延续到 3 月。不能据此认定这 162 条样本都错了，也不能直接更新初始画像。其余 220 户“没有记录变化详情”，不等于证明资料始终不变。

识别变化只使用 `Aq1_2` 至 `Aq1_10` 的明确选项。`Aq1_1` 的题干带有 “No” 后缀，未用其 Yes/No 极性推断稳定性。原始选项、占位符及行号保存在 `sources/`，没有把 `NA` 或 `-` 解释为电器不存在。

## 复现

Python 3.9+，无额外依赖。在仓库根目录运行：

```bash
python3 scripts/build_iflex_context_extension.py --output /tmp/iflex-context-rebuild
python3 -m unittest discover -s tests -p 'test_iflex_context_extension.py' -v
```

默认使用本目录随附的来源摘录。`sources/regional_temperature.jsonl.gz` 按地区与小时去重；`sources/survey2_change_answers.jsonl` 仅保留现有家庭的相关问答。构造时已逐条检查原始小时记录与父样本历史电量一致，再提取同一行的温度；检查规模和源文件哈希见 `sources/extraction.json`。这些来源摘录用于复现，不是训练输入。

如要从本版已校验的 `iflex_candidates.csv` 原始小时切片及 Zenodo v2 的问卷重新提取：

```bash
python3 scripts/build_iflex_context_extension.py \
  --hourly-csv /path/to/iflex_candidates.csv \
  --survey-dir /path/to/iflex/v2 \
  --source-dir /tmp/iflex-context-fresh/sources \
  --output /tmp/iflex-context-fresh
```

该模式要求小时切片与 v1 原始读数哈希一致，并核对两份问卷文件的发布方 MD5。它不是任意新版数据导入接口。`manifest.json` 固定父版本、代码、来源摘录及输出的哈希。

## 来源与许可

Hofmann 与 Siebenbrunner 的 [iFlex 数据说明论文](https://doi.org/10.1016/j.dib.2023.109571)：表 5 给出问卷时间，表 7 给出气象站，表 11 定义温度字段。[原始数据 v2](https://doi.org/10.5281/zenodo.8248802) 采用 CC BY 4.0。天气原采集方为 Norwegian Meteorological Institute。这里仅按现有样本窗口选择观测并整理问卷选项，未改变读数、补填家庭事实或训练模型。
