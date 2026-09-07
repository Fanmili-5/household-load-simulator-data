# 家庭负荷模拟模型数据：SGSC / iFlex

2026-09-08 已实际更新两份完整数据的家庭画像：iFlex 补回家庭成员、经济资料、设备数量、偏好和使用习惯；SGSC 补回同户记录中的节电努力、互联网接入等信息。原始回答、异常标记和信息时点说明一并保留。详见 [本次更新](docs/PROFILE_UPDATE_20260908.md)。原始来源没有提供的信息仍为未知。

本仓库提供 SGSC 和 iFlex 的同户家庭观测、构造脚本、字段定义及验证记录。研究思路、论文依据、方案取舍和后续计划统一维护在 [Notion](https://app.notion.com/p/3d406135328a817f94d9d1918f323c89)。

| 数据 | 家庭数 | 记录数 | 当前答案覆盖范围 | 时间粒度 |
|---|---:|---:|---|---|
| SGSC（澳大利亚） | 2,078 | 16,342 | 活动期间，2–4 小时 | 半小时 |
| iFlex（挪威） | 314 | 2,071 | 活动当天，24 小时 | 小时 |

**当前完整文件是观测数据，尚未发布全量 SFT 数据。** 同一家庭可以出现多次；SGSC 全量仍保留活动窗口答案。仓库另有两条全天示例和两条使用部分画像的消息格式演示，不能将这些示例的完成状态推广到全量。

## 先看哪里

- 每户一行的画像表：[SGSC](tables/sgsc_households.csv) · [iFlex](tables/iflex_households.csv)，先看家庭和习惯更方便。
- 按活动查看汇总表：[SGSC 汇总表](tables/sgsc_events.csv) · [iFlex 汇总表](tables/iflex_events.csv)。每行对应一户的一次活动，包含家庭特征、设备信息、活动日期、时长及实测电量统计。空白表示未知或不适用。
- 下载完整曲线：[SGSC](data/sgsc.jsonl.gz) · [iFlex](data/iflex.jsonl.gz)。点击文件页的 Download raw file，或直接克隆仓库。Gzip 只压缩文件，历史及答案序列均完整保留。
- 了解一条当前记录：[SGSC 普通单表家庭](examples/sgsc_single_observation.json) · [SGSC 两表合计家庭](examples/sgsc_two_meter_observation.json) · [iFlex 家庭](examples/iflex_observation.json)。这些样例已同步到扩展画像版本。
- 查看后续全天格式：[SGSC 全天样例](examples/sgsc_full_day_example.json) · [iFlex 全天样例](examples/iflex_full_day_example.json)。这是另行核验的两个格式示例，不额外计入上表。
- 查字段：[字段说明](docs/FIELDS.md) · [来源字段覆盖](docs/PROFILE_COVERAGE.md)。
- 查是否漏提取：[逐字段复核及修正](docs/EXTRACTION_AUDIT_20260908.md)。家庭表和活动表的 `profile_appliances` 均保留完整设备列表；SGSC 反馈技术的启用时间仍待核实。
- 查构造格式与示例：[版本、字段映射及消息转换](docs/CONSTRUCTION_FORMAT.md)。这里分别列明全量观测、全天例子和部分画像演示的范围及检查命令。

## 怎样读取

Python 3.10 及以上即可运行，不需要安装额外依赖：

```bash
git clone https://github.com/Fanmili-5/household-load-simulator-data.git
cd household-load-simulator-data
python3 scripts/verify_release.py
python3 scripts/read_data.py
```

读取一条完整记录：

```python
from scripts.read_data import read_records

sample = next(read_records('sgsc'))
print(sample['input']['profile'])       # 家庭与设备
print(sample['input']['history'][0])    # 第一天历史用电
print(sample['input']['context'])       # 活动条件
print(sample['target']['energy_kwh'])   # 活动窗口每个时段的家庭电量
```

如果使用 pandas，可直接打开汇总表：

```python
import pandas as pd
df = pd.read_csv('tables/iflex_events.csv', dtype={'household_id': str})
print(df[['household_id', 'event_date', 'household_size', 'target_total_kwh']].head())
```

## 电量怎样合计

SGSC 合并为一份家庭数据。登记为只有一块普通供电表的家庭，使用该表电量；登记为普通供电加受控负荷两块表的家庭，使用两表逐时段之和。两组家庭不重复，本次均不包含登记有发电或其他表计的家庭。

统一读取 `target.energy_kwh` 和 `input.history[].energy_kwh` 即可。原分路读数和表计类型仍在记录中，方便需要时检查。受控供电可能涉及外部控制，因此电量减少不能单凭读数解释为住户主动节电。iFlex 沿用来源提供的家庭需求电量。

## 筛选与来源

SGSC 原有 16,600 条观测，其中 258 条存在日期、产品条件冲突或边界信息缺失，未放入本次数据文件；记录及原因见 [剔除表](tables/sgsc_exclusions.csv)。保留记录中另有 1,526 条缺少招募表产品字段的辅助佐证，但同户资料、事件与负荷证据仍在，已单独标记，便于做敏感性比较。

设备数量未知就保留未知；问卷中的“不使用”不改成“没有设备”。现有历史参考与实测答案分别保存，未生成住户同意标签，也未训练模型。

原始来源、许可及本次整理内容见 [数据署名与许可](DATA_LICENSES.md)。导出清单、源批次哈希和核验结果在 [provenance](provenance/)。
