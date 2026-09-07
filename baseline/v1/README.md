# 家庭模拟数据 baseline v1.0.0

固定格式：`household-baseline/1.0.0`。本目录交付两份来源的同户家庭画像和完整家庭日观测。数据成员、字段、转换规则、时间窗口及文件哈希由本目录的清单定义。

| 来源 | 家庭画像 | 完整家庭日 | 历史 | 答案 |
|---|---:|---:|---|---|
| SGSC | 2,078 户 | 16,330 条 | 此前七天，336 点 | 全天 48 个半小时 kWh |
| iFlex | 314 户 | 2,071 条 | 此前七天，168 点 | 全天 24 个小时 kWh |

合计 2,392 户、18,401 条完整日样本。SGSC 原保留活动记录中的 12 条在完整八天窗口内存在缺失或重复读数，未填补；见 [窗口剔除记录](provenance/window_exclusions.json)和验证报告中的具体时间标签。此前已剔除的 258 条活动条件冲突记录没有重新引入。

## 交付文件

| 内容 | 文件 |
|---|---|
| 全部家庭日；每行含完整语义画像、历史、条件、答案 | [SGSC](data/sgsc.jsonl.gz) · [iFlex](data/iflex.jsonl.gz) |
| 每户一行的画像及逐字段来源、原回答和质量标记 | [SGSC](profiles/sgsc.jsonl.gz) · [iFlex](profiles/iflex.jsonl.gz) |
| 机器可检查的格式 | [家庭 schema](schema/profile.schema.json) · [样本 schema](schema/sample.schema.json) |
| 设备目录、分类值 | [20 类设备](schema/appliance_catalog.json) · [本批分类值](schema/category_values.json) |
| 每个源字段的去向 | [46 列 SGSC + 96 列 iFlex](provenance/source_field_mapping.csv) |
| 各字段已知与未知的实际覆盖 | [字段覆盖](provenance/profile_field_coverage.csv) |
| 两条完整样例 | [SGSC](examples/sgsc.json) · [iFlex](examples/iflex.json) |
| 对应消息渲染示例 | [SGSC](examples/sgsc_messages.json) · [iFlex](examples/iflex_messages.json) |
| 按家庭划分的固定索引 | [household_holdout.csv](splits/household_holdout.csv) |
| 版本、数量与文件校验值 | [manifest.json](manifest.json) · [validation.json](validation.json) |

## 一条记录怎样读

`input.profile` 含家庭成员、住房、设备清单、能源服务、使用习惯、偏好及逐车资料。两个来源的字段定义和设备目录相同；`null` 表示未知，`false` 表示明确否，设备 `count=0` 可由明确不存在转换得到。每个设备都保留类别、持有、数量、子类型和参数位置，不能将全部设备的数量直接相加：可逆空调与热泵等类别可能重叠。

`input.history` 是目标日零点以前连续七天的区间电量；`input.context` 指定预测起点、一天的目标窗口、原始时间粒度、国家和地区、计量范围及当天活动。时间按来源时钟表达，未假定 UTC 偏移；24 小时表示源时钟上的完整日。每个值的时段由起点、数组位置和间隔共同确定。

`output.energy_kwh` 是同一户当天实测整户电量。SGSC 先将结束标签转换成区间，单表家庭采用普通供电，两表家庭逐点合计普通供电与受控负荷。原活动答案与新全天答案的对应片段逐点相符。iFlex 保留源家庭需求口径；其价格仍是实验奖励信号，不是零售电费。

`metadata` 记录同户来源、原始记录 ID、读数文件哈希、活动证据状态和输入时间可得性。原问卷、采集状态及转换依据放在每户画像文件中，用 `metadata.profile_id` 关联；这些追溯资料不发送给模型。

## 字段转换规则

- 人数、年龄和生活状态独立保存；生活状态可能重叠，不强行求和。年龄分布矛盾时整组未知，原回答保留。
- 面积、建筑年份和收入保留区间边界及开闭状态，不填中点。收入题未在本轮确认统计周期，`period=null`。
- 受访者性别与全户信息分开。来源归纳的房型与自报房型分别保存，不自动补值。
- “不用某种方式供暖”进入服务用途，不能变成设备不存在。热泵用于供暖和热水也不能据此计成两台；地源供暖、区域或共用供暖作为服务描述保留。
- 供暖、热水控制与一般习惯明确关联对象。时间段、频率等级按原意归一化，不生成逐日作息。
- 电动车数量和逐车充电习惯一一关联；充电地点保留是否与家庭共表的信息。额定功率、设备轨迹和调整理由没有实测就不构造。
- 光伏配套电池问题只表示该关系，不能据此推断全户储能持有。短信联系授权放在管理资料中。

目录中的 20 类设备表示框架能容纳这些类别，不表示来源完整调查了这些设备。各字段覆盖以本批统计为准；未知原因可追溯到每户原始记录。

## 验收与使用状态

本次交付是构造完成的观测数据 baseline；已实现全量语义映射、完整日重建、固定格式、源字段对账及消息转换接口。正式模型训练尚未运行。

每户问卷具体采集时刻和每次活动通知实际送达时刻尚未全部确认，数据中明确保留未核实状态。因此 `formal_training_release=false`。iFlex 记录了前一天下午通知的协议说明，但没有将协议时间充当每户实际送达时间。该状态不表示文件无法读取或监督答案不存在。

固定划分按来源内的家庭数约 70%/15%/15%，同户所有日期进入同一分区。同一日期可出现在不同分区，所以该划分用于未见家庭，不宣称检验未见活动日期。按日期或跨地区的试验可另建索引，不能改写本版索引的含义。

## 读取、验证和复现

在仓库根目录执行；读取和默认校验使用 Python 标准库：

```bash
python3 scripts/read_baseline.py --source sgsc
python3 scripts/verify_baseline.py
python3 -m unittest discover -s tests -v
```

使用独立 JSON Schema 实现校验：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-baseline-qa.txt
.venv/bin/python scripts/verify_baseline.py --reference-json-schema
```

仅使用本仓库的固定窗口输入即可重建，不需要本地研究工作区：

```bash
python3 scripts/build_baseline.py --window-cache baseline/source_windows_v1/windows.jsonl.gz --output outputs/rebuilt_baseline
python3 scripts/verify_baseline.py --root outputs/rebuilt_baseline
```

[固定窗口输入](../source_windows_v1/README.md)是经核验的抽取结果，区别于原始 CSV。其哈希记录在本版清单中。

从本地原读数重新抽取窗口并重建：

```bash
python3 scripts/baseline_windows.py --pipeline-root /path/to/load_response_pipeline
python3 scripts/build_baseline.py
python3 scripts/verify_baseline.py --pipeline-root /path/to/load_response_pipeline --write-report
```

所需原始文件及哈希见 [raw_curve_sources.json](provenance/raw_curve_sources.json)。脚本不下载或补造缺失读数；公开仓库已有的旧观测提供经过检查的同户画像和候选成员。原问卷到旧观测的重建入口仍见 [画像更新说明](../../docs/PROFILE_UPDATE_20260908.md)。

完整渲染一个分区的 SFT 候选文件：

```bash
python3 scripts/export_baseline_sft.py --split train --output outputs/baseline_train.jsonl.gz
```

渲染仅将完整输入和真实答案转换为 `system/user/assistant`，保留逐条未核实状态；不生成新的标签，不启动训练。模型上下文长度、数值编码和答案损失掩码属于实际接入训练时的检查。

本版原始数据许可沿用 [DATA_LICENSES.md](../../DATA_LICENSES.md)。数据选择、文献和研究取舍统一记录在 [Notion](https://app.notion.com/p/3d406135328a817f94d9d1918f323c89)。
