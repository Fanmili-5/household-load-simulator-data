# 家庭负荷模拟 benchmark v1.0.0

本版定义回顾性整户负荷预测任务：输入同户家庭资料、此前七天用电和已记录的目标日活动条件，输出完整一天的实测区间电量。数据来源为 SGSC 和 iFlex。版本标识为 `household-benchmark/1.0.0`。

| 来源 | 有保留样本的家庭 | 保留家庭日 | 隔离家庭日 | 目标日期数 |
|---|---:|---:|---:|---:|
| SGSC | 2,076 | 16,246 | 84 | 21 |
| iFlex | 314 | 2,071 | 0 | 11 |

两份来源共 18,317 条保留家庭日、2,390 户。画像文件保存原来全部 2,392 户，因此画像户数与保留样本户数不同。旧版 18,401 条完整日中隔离 84 条，其余全部保留。更早的 12 条不完整窗口和 258 条条件冲突记录没有重新引入。

## 文件与字段

| 文件 | 内容 |
|---|---|
| [SGSC 数据](data/sgsc.jsonl.gz)、[iFlex 数据](data/iflex.jsonl.gz) | 每行一户一天，完整 input/output/metadata |
| [SGSC 画像](profiles/sgsc.jsonl.gz)、[iFlex 画像](profiles/iflex.jsonl.gz) | 每户语义字段、原回答及转换依据 |
| [SGSC 样例](examples/sgsc.json)、[iFlex 样例](examples/iflex.json) | 两条可直接阅读的完整样本 |
| [画像 schema](schema/profile.schema.json)、[样本 schema](schema/sample.schema.json) | 机器可检查的字段约束 |
| [隔离索引](quarantine/index.csv) | 原分区、样本 ID 和隔离原因 |
| [SGSC 隔离原值](quarantine/sgsc.jsonl.gz) | 保留完整输入与答案，默认读取和导出不包含这些记录 |
| [字段覆盖](provenance/profile_field_coverage.csv) | 按全部画像统计已知/未知，不能将固定类别名称计入设备信息覆盖率 |
| [源字段去向](provenance/source_field_mapping.csv)、[画像修正](provenance/profile_corrections.json) | 142 列对账，以及 22 户跳题逻辑修正 |
| [质量标记](provenance/quality_flags.json)、[原读数复核](provenance/zero_review.json) | 具体窗口、连续零时长、每日电量及相邻读数证据 |
| [时间和费率依据](provenance/input_evidence.json) | 来源、证据等级和未解决的来源缺口 |
| [评测协议](evaluation/protocol.json)、[家庭划分](splits/household_holdout.csv) | 任务、成员、输入版本和指标 |
| [清单](manifest.json)、[校验](validation.json) | 生成文件哈希、数量及校验结果 |

`input.profile` 固定包含家庭成员、住房、设备、能源服务、习惯、偏好和逐车资料。`null` 是未知，`false` 是明确否；数量不随意填 1。20 类设备目录表示框架容量，不表示来源调查完整。空调与热泵等类别可能重叠，不计算设备总数。

`input.history` 是此前七天；SGSC 为 336 个半小时值，iFlex 为 168 个小时值。`input.context.target_window` 定义源时钟上的完整日与间隔。数组位置、起点和间隔共同确定时段，未假定 UTC 时差。

`output.energy_kwh` 是当天整户实测电量，SGSC 48 点、iFlex 24 点。SGSC 单表采用普通供电，双表逐点合计普通供电与受控负荷；iFlex 保留源家庭需求口径。没有逐电器动作、反事实负荷或同意标签。

`metadata` 包含质量、时间证据和适用范围，不进入模型输入。特别是质量标记和每日总量使用了目标值，只用于固定数据集筛查，不能作为预测特征。

## 本版修正

1. **零读数隔离。** 历史和目标组成的八天窗口中，任何连续至少 24 小时全零的样本进入隔离区，包含跨午夜的零段。41 条目标日全零、21 条八天全零均包含在 84 条隔离记录内，不重复相加。原始文件与构造数值一致，现有服务状态无法确定零读数原因。全零不被自动解释为设备故障或无人居住。
2. **近零只标记。** 每个源时钟日总量在 `(0, 0.01] kWh` 时增加复核标记；这是本版操作性筛查阈值，不是文献给定的异常判据。仅因近零而被标记的 4 条记录保留。阈值变化需要新版本。
3. **无车跳题。** iFlex 22 户 `q16_bil=No` 且后续车辆问题没有矛盾回答，归一化为汽车数 0、电动车持有 false、数量 0、逐车列表为空，影响 149 条样本。逻辑依据写入逐字段追溯，原问卷 NA 保留。

筛查使用了目标日，因此本版结果只能解释为在筛查后窗口上的表现，不能当作上线时可预先执行的筛选，也不能代表全部住户的平均表现。保留隔离记录用于后续定因与敏感性分析。

## 适用范围与输入时间

当前可用的是 `retrospective_conditional`：给定已记录资料的回顾性条件预测。iFlex 原文说明 Survey 1 在参加试验前完成，第一阶段通知在前一天 15:00 发送；SGSC 报告说明提前 24 小时通知。协议证据不等于每户收到或阅读消息的记录。

逐户输入采集及通知送达时刻未完全核实，`strict_prospective` 集合为空，接口拒绝将回顾性数据按这个严格范围导出。样本继承的 `formal_training_release=false` 不表示真实答案不可用于回顾性研究；它不构成已验证输入时间或模型训练接口的声明。本次未训练模型。接入具体模型时仍需核对 tokenizer、上下文长度、答案损失掩码和数值输出解析。

SGSC 数值费率尚无逐户合同依据，因此保持未知；不将论文报告的通用费率或由事后奖励反推的费率写进输入。当前 SGSC 支持活动类型/时段条件，iFlex 支持记录的实验价格条件。iFlex 实验价格不等于零售电费。

## 固定划分与输入比较

| 来源 | train | validation | test |
|---|---:|---:|---:|
| SGSC | 11,432 | 2,405 | 2,409 |
| iFlex | 1,449 | 304 | 318 |

沿用旧版家庭分区，隔离后不重新随机分配。日期跨分区重叠，评测未见家庭，不能宣称未见活动日期或跨国迁移能力。

输入版本为 `history_only`、`history_profile`、`history_context`、`full` 和 `full_without_daytime_home`。前两种不提供活动类型、价格、国家和地区，但保留目标窗口、时钟及计量范围以解释输出。去掉白天在家字段时仅移除对应习惯条目，其他信息保持一致。比较时必须使用同一批样本、相同家庭划分和训练预算。

保留后的 SGSC 高峰价格惩罚组 7,350 条均为白天在家，奖励组 8,896 条均为白天不在家，见[分组交叉表](provenance/event_home_cross_table.json)。分别评分和去字段比较可以揭示预测对该信息的依赖，但不能消除原始混杂，或识别居家习惯的独立作用。

## 评分接口

提交 JSONL，每行仅包含 `sample_id` 和 `energy_kwh`。必须覆盖所选来源和分区的全部样本，输出原生长度与 kWh 单位。重复、缺失或多余 ID，错误长度、布尔值、负数、非数值及 NaN/Infinity 均使整次评分失败，不静默删除失败样本。

```bash
python3 scripts/evaluate_benchmark.py --predictions outputs/predictions.jsonl --split test --variant full --source both --output outputs/scores.json
```

主指标为小时平均功率 MAE。SGSC 两个相邻半小时电量先相加为小时电量，iFlex 不变；小时 kWh 除以 1 小时即小时平均 kW。辅助指标为小时 RMSE、全天总电量绝对误差、小时峰值绝对误差，以及活动窗口总电量绝对误差。一个样本有多个活动时，活动误差先在样本内平均。

各项指标先在同户样本内平均，再在每个来源内等权平均家庭；两来源汇总等权平均来源。分别报告来源和来源内活动类型结果。这里的 RMSE 是逐日 RMSE 再按上述规则平均，区别于对所有时点一次求 RMSE。小时评分会平滑半小时变化，不用于声称半小时峰值准确度。

预处理仅在 train 拟合，validation 用于选参数；测试前固定模型版本、输入版本、随机种子和设置。`--variant` 是提交者声明，评分器仅凭数值预测无法证明实际用了哪个输入，研究结果需附模型配置。没有参考模型排名或 SFT 优势声明。

## 读取、导出和复现

```python
from scripts.benchmark_io import read_samples
sample = next(read_samples("sgsc", split="train"))
```

```bash
python3 scripts/benchmark_io.py --split train --track retrospective_conditional --variant full --output outputs/benchmark_train.jsonl.gz
python3 scripts/verify_benchmark.py
python3 -m unittest discover -s tests -v
```

仅使用公开仓库重建，输出目录必须尚未含清单，以防混入旧文件：

```bash
python3 scripts/build_benchmark.py --output outputs/rebuilt_benchmark
python3 scripts/verify_benchmark.py --root outputs/rebuilt_benchmark
```

独立 JSON Schema 校验沿用根目录 `requirements-baseline-qa.txt`。原读数零段复核可用本地原始数据重跑：

```bash
python3 scripts/audit_benchmark_zeros.py --pipeline-root /path/to/load_response_pipeline --output outputs/zero_review.json
```

旧的 [baseline/v1](../../baseline/v1/README.md) 及 `baseline-v1.0.0` 标签完整保留。它是本版的可验证构造输入，旧脚本、旧数据和旧划分没有被改写。来源许可与修改署名见 [DATA_LICENSES.md](../../DATA_LICENSES.md)。
