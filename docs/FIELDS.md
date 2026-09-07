# 字段怎样读

两个压缩文件都是 JSONL，每行一个 JSON 对象。统一的是外层结构及家庭合计电量字段，活动条件和问卷仍保留来源含义。

| 字段 | 内容 |
|---|---|
| `source`、`sample_id`、`household_id`、`event_id` | 数据集、样本、匿名家庭和事件标识。跨源关联必须同时带上 `source`，不能按相似户号拼接。 |
| `input.profile.household` | 同户问卷资料。SGSC 保留原列名；iFlex 的 q4 房型、q5 面积、q6 自有住房、q7 建造年代、q19 人数、q23 白天在家。 |
| `input.profile.people` | 整理后的家庭人数、年龄分布、生活状态、教育、收入和家庭类型。异常年龄分布留空。 |
| `input.profile.dwelling` | 住房类型、面积、产权、建造年代、改造与合住等信息；未采集项为 `null`。 |
| `input.profile.preferences` / `usage_habits` | 舒适温度、在家情况、温控和设备使用习惯。问卷的一般习惯，不是活动日的实测操作。 |
| `input.profile.energy_attitudes` / `energy_systems` | 用电与价格关注、节电努力、互联网接入、合同及能源用途。 |
| `input.profile.vehicles` | 车辆持有和数量，以及按车辆序号关联的充电信息。未知车辆配置为 `null`，明确无电动车时逐车列表为空。 |
| `input.profile.appliances` | 电器类别、持有状态、数量及原始回答。`null` 表示未知；`false` 表示已知不持有。iFlex 供暖题的 No 表示不用该方式供暖，所以 `present` 仍可能为 `null`。 |
| `input.history` | 七个来源日期的用电列表，每天都有 `energy_kwh`。SGSC 每天 48 点，iFlex 每天 24 点。 |
| `input.context` | SGSC 的活动类型、起止和产品代码；iFlex 的当天 24 点实验价格等。 |
| `target.energy_kwh` | 该户在目标窗口每个区间的合计实测电量，单位 kWh。读取这一字段即可，无需自行再次叠加分路。 |
| `target.channels_kwh` | SGSC 各分路原值，用于回查；其中电量已按适用范围计入合计，不能再把各通道与合计一起相加。 |
| `estimated_reference` | 已有流程估计的历史参考，可为 `null`。这是单独保存的辅助量，不是真实无活动反事实。 |
| `metadata` | 原批次、源行号、表计类型、条件证据分组、原核验状态。不是模型输入。 |
| `metadata.profile_provenance` | 同户原回答、来源文件哈希、含表头的记录编号、字段来源与状态、异常和采集时点说明。管理或事后字段只保存在这里。 |

## 时间

SGSC 的 `timestamps` 和 `interval_end_labels` 是半小时时段的**结束标签**。例如 14:00 对应 13:30–14:00 的电量。旧批次历史按标签日期保存，第一天 00:00 对应前一日 23:30–00:00，最后一天 23:30 对应 23:00–23:30。因此本次历史是连续 336 点，但还不是按“活动日零点往前精确七天”重新切好的全天训练输入。新的完整日样例已单独调整，见 examples。

iFlex 保留 Date/Hour 坐标，Hour 1 表示源日期的第一个小时，展示为 00:00–01:00；Hour 24 是 23:00–次日 00:00。本次未声称已经统一到 UTC。分析先按各数据源自己的时间坐标进行。

SGSC 活动类型 DPR 对应节电奖励、DPP 对应高峰价格惩罚安排。具体户级数值费率尚未核实，`incentive_rate` 保留为空；不能把空值当作免费。iFlex 的价格是实验奖励计算信号，不是住户实际零售电费。

## 汇总表

`tables/*_events.csv` 不包含长曲线，适合筛选和分组。主要派生列如下：

| 列 | 定义 |
|---|---|
| `window_hours` | 实测答案覆盖的小时数，SGSC 为 2、3、3.5 或 4；iFlex 为 24。 |
| `target_total_kwh` | 窗口内区间电量之和。 |
| `target_mean_kw` | 总电量 / 窗口小时数。 |
| `target_max_interval_mean_kw` | 各区间电量 / 区间小时数后取最大值，是区间平均功率的最大值，非瞬时尖峰。 |
| `existing_reference_total_kwh` | 原清洗批次已经保存的参考曲线总量；没有参考则为空。 |
| `delta_vs_existing_reference_kwh` | 实测总量减上述参考总量；正数为更高，负数为更低。不是活动的净因果效应。 |
| `*_present` / `*_count` / `*_answer_raw` | 持有状态、设备数量和来源回答；不同信息不能互换。 |
| `meter_configuration` | SGSC 单表或两表合计，仅作计量说明。数据已合并在同一个 SGSC 文件。 |
| `evidence_group` | 条件证据状态，含缺辅助产品佐证但保留的记录。 |

CSV 空白统一表示未知或不适用，完整 JSON 保留更细的区别。SGSC 的原房型与归纳房型各有一列，没有自动相互补值；iFlex 的人数等字段也未跨源补给 SGSC。

新增的 `profile_*` 列对应扩展画像；字典和列表用 JSON 单元格保存。`*_households.csv` 每户一行，不重复活动；`*_events.csv` 每条活动一行。`profile_quality_flags` 用于筛查异常。旧字段清单及新增处理详见 [画像更新](PROFILE_UPDATE_20260908.md)。
