# LIRNEasia 真实家庭次日用电 benchmark 扩展 v1.0.0

**新数据已实际加入：默认读取 410 户、6,325 个家庭日；另完整保存 335 个隔离窗口。** 这来自全量核验的 422 户、6,660 个连续窗口。版本为 `lirneasia-day-ahead/1.0.0`，独立于冻结的 SGSC/iFlex `benchmark/v1`。

一条样本的任务是：**同户 W1 家庭与多设备资料 + 此前连续 7 天电网购电量 + 目标日历 → 次日 96 个 15 分钟实测购电量。** 不是 ResStock 或其他仿真输出，不包含实际调控事件、费率或住户同意标签。

## 直接获取

- [默认数据 JSONL.gz](data/lirneasia.jsonl.gz)：6,325 条完整 input/output/metadata。
- [完整可读样例](examples/lirneasia.json)：`ID0053`，2024-04-20—26 历史 → 04-27 目标。
- [固定划分](splits/household_holdout.csv)：包括保留与隔离样本的 status。
- [隔离原记录](quarantine/lirneasia.jsonl.gz)、[逐窗零读数复核](evaluation/zero_reading_review.json)：335 条，原值完整保存。
- [源摘录](sources/)：422 户原问卷字段、1,043 段累计电表读数，可以不下载 1.70 GB 原文件就重建当前发布窗口。
- [构造检查](verification.json)、[源文件校验](provenance/source_integrity.json)、[发布清单](manifest.json)。
- [全项目构造依据与细节](../../docs/DATA_CONSTRUCTION.md)。

## 核验与筛选

原 `smart_15min_2.csv` 已完整取得：1,696,953,202 字节，16,425,676 条读数、2,878 个户号。MD5 和原 Zenodo ZIP 成员 CRC 均通过。画像、设备、成员及问卷日期等 8 个完整调查 CSV 也已核对原文件；不是由项目宣传的约 4,000 户推定可用规模。

从原 `date + time` 构建时间轴，相邻两个唯一端点必须相差 900 秒，累计电量有限且不下降；`import(t+15m) - import(t)` 为该区间 kWh。缺点、重复、重置均不通过，不跨缺口求差，不插值或补零。每天必须有 96 个完整区间，8 个连续整日需要 769 个累计端点。

家庭严格条件为单电表、无家庭经营、明确无共享租客/寄宿者情形、有效人口和面积、已知房型和社会经济类别；成员数与家庭表一致且成员 ID 唯一、年龄有效；至少两种普通家电；W1 报告无太阳能及其他自发电、备用发电机或储能。保留片段实际出口电量增量为零。问卷日必须严格早于历史开始日，不使用 W2/W3 回填早期输入。

据此得到 422 户、1,043 个连续 8—37 天片段，共 6,660 个窗口、1,340,256 个不重复计数的实测区间。8 天完整性通过只说明能构造窗口。进一步沿用主 benchmark 的 **连续至少 24 小时精确零读数**规则，335 条单独隔离，其中 12 户没有保留窗口，默认集因此为 **410 户、6,325 条**。零值原因未定，不改写成故障或无人居住。所有样本和原始源摘录仍可追溯。

## 样本字段与时间

| 字段 | 含义 |
|---|---|
| `input.profile.household` | 人数、住房、教育职业、社会经济类别及月支出等 W1 原字段；月支出不是收入 |
| `input.profile.demographics` | 成员年龄、关系、性别、活动和在家时长等；条件跳题保留为空 |
| `input.profile.appliances/ac_roster/fan_roster/light_roster` | 原始设备及使用记录；没有记录的类型不自动等同于没有设备 |
| `input.profile.generation` | W1 发电、热水和烹饪调查原字段 |
| `input.history` | 672 个 15 分钟 kWh，左闭右开 `[history_start, forecast_origin)` |
| `input.context` | 预测起点、24 小时目标窗口、间隔、计量范围和目标星期 |
| `output.energy_kwh` | 96 个未来 15 分钟电网购电量 |
| `metadata` | 户号、来源、划分、问卷日期、质量与证据边界；不传给模型 |

语义输入删除原户号/成员号/设备号等追溯键，不包含答案、质量筛选值、后续问卷。原始追溯键保留于 `sources`。本扩展保留原生问卷模块，没有冒充和 SGSC/iFlex 完全同构的画像 schema。原生日期时钟未另行猜测 UTC 偏移；来源的电表数据可得延迟尚未独立验证，所以不声称已证明在线实时可用。W1 快照也不证明设备之后从未变化。保留样本中问卷距目标日为 8—227 天，样本中位数 124 天；“上周使用时长”等字段指调查前一周，不能转述为预测日前七天的行为。

## 固定划分与评分

先对 422 个户号按 `SHA256('lirneasia-household-v1:' + household_ID)` 排序，分配 floor(70%)/floor(15%)/余数；隔离之后不重分配。按家庭划分防止同户重叠滑动窗口进入不同集合。

| 分区 | 初始画像户数 | 有保留样本的户数 | 默认样本 | 隔离样本 |
|---|---:|---:|---:|---:|
| train | 295 | 287 | 4,309 | 282 |
| validation | 63 | 62 | 911 | 14 |
| test | 64 | 61 | 1,105 | 39 |

`history_only` 和 `history_profile` 使用相同样本和划分，二者都保留目标日历与计量范围，后一项额外加入家庭资料。划分主要考察未见家庭，日期可能重叠，不能据此声称未见未来日期的泛化。

主指标是小时平均功率 MAE：每四个 15 分钟 kWh 相加为小时电量，除以 1 小时得到平均 kW。先平均同户各日误差，再等权平均家庭。辅助指标为小时 RMSE、全天电量误差、小时峰值误差和原生 15 分钟平均功率 MAE。没有事件标签，因此没有事件响应评分；不与 SGSC/iFlex 自动混成统一排名。重复/缺失/多余预测 ID、长度错误、负值、布尔值和非有限数会使整次评分失败。

```bash
# 从仓库根目录；仅用 Python 标准库
python3 scripts/verify_lirneasia_extension.py
python3 scripts/build_lirneasia_extension.py --output outputs/lirneasia_rebuilt
python3 scripts/verify_lirneasia_extension.py --root outputs/lirneasia_rebuilt
python3 -m unittest discover -s tests -v
```

```python
import sys
sys.path.insert(0, 'scripts')
from lirneasia_io import read_samples, model_input
sample = next(read_samples('train'))
x = model_input(sample, 'history_profile')
y = sample['output']['energy_kwh']
```

预测提交每行仅含 `sample_id` 与 96 个值的 `energy_kwh`：

```bash
python3 scripts/lirneasia_io.py --predictions outputs/predictions.jsonl \
  --split test --variant history_profile --output outputs/lirneasia_scores.json
```

## 从完整原始文件复现准入名单

默认构建从仓库源摘录重建已选择窗口，不宣称重新筛查未发布的原始全集。复现全量准入筛选时，将下列原文件放在同一目录：`smart_15min_2.csv`、`survey_dates.csv`、`w1_household_information_and_history.csv`、`w1_demographics.csv`、`w1_appliances.csv`、`w1_ac_roster.csv`、`w1_fan_roster.csv`、`w1_light_roster.csv`、`w1_electricity_generation_water_heating_cooking.csv`。作者提供 [Zenodo](https://zenodo.org/records/15023048) 与 [Kaggle](https://www.kaggle.com/datasets/lirneasia/sri-lankan-residential-electricity-consumption)。

安装 DuckDB CLI 并将其放在 PATH 后：

```bash
python3 scripts/audit_lirneasia_raw.py --raw-root /path/to/original_csvs \
  --output outputs/lirneasia_full_raw_audit
```

脚本先核对全部原 CSV SHA256，再执行 [全量 SQL](provenance/full_cohort_audit.sql)，应重现 422 户和 6,660 个窗口。之后发布构建器执行相同的连续零读数隔离。三份来源许可和本次修改见 [DATA_LICENSES.md](../../DATA_LICENSES.md)。目前完成数据、固定划分及评分接口，没有训练模型或证明画像带来预测提升。
