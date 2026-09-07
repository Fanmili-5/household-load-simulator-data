# 旧观测与早期格式示例

当前完整交付见 [baseline v1.0.0](../baseline/v1/README.md)。以下说明保留原观测和早期片段的历史格式，不代表当前交付状态。

本页说明仓库实际文件的格式、转换和检查方法。研究依据与待定设计见 [Notion](https://app.notion.com/p/3d406135328a817f94d9d1918f323c89)。当前完整文件是观测记录；统一家庭框架和 SFT 格式尚未全量发布。

## 文件与版本

| 文件 | 版本 | 实际范围 |
|---|---|---|
| `data/*.jsonl.gz` | `household-observation-share/2` | SGSC 16,342 条、iFlex 2,071 条。SGSC 答案为活动中 2–4 小时，iFlex 为全天。 |
| 完整文件中的 `input.profile` | `household-baseline-profile/2` | 已扩展的同户画像；部分字段仍保留源问卷表示，不是已冻结的新框架。 |
| `examples/*_full_day_example.json` | `household-day-example/2` | 两户完整日示例，画像为现有扩展版本，历史和答案已单独对齐。 |
| `examples/framework_design/*_profile_fragment.json` | `household-framework-design/0.1` | 两户的部分字段映射；仅含六类设备条目，不能当作完整画像。 |
| `examples/sft_format/*_messages.json` | `sft-format-demo/0.1` | 两条消息格式演示，使用上述画像片段及同户完整日曲线；`formal_training_release=false`。 |

现有全量字段见 [FIELDS](FIELDS.md)，逐字段处理范围见 [提取复核](EXTRACTION_AUDIT_20260908.md)和[来源字段覆盖](PROFILE_COVERAGE.md)。

## 画像映射片段

[SGSC](../examples/framework_design/sgsc_profile_fragment.json) 与 [iFlex](../examples/framework_design/iflex_profile_fragment.json) 的 `input_fragment` 包含 `household`、`appliances`、`energy_services`、`usage_habits` 和 `preferences`；每条转换依据在 `metadata.field_mapping` 中。

六类设备均为 refrigerator、air_conditioner、clothes_dryer、pool_pump、heat_pump、electric_water_heater。每项使用相同的键：

```json
{
  "type": "air_conditioner",
  "present": true,
  "count": null,
  "subtype": "split_system",
  "rated_power_w": null
}
```

- `present` 为 `true`、`false` 或 `null`；数量和功率未知时为 `null`，不填成 1 或典型功率。
- 数量表示实物设备台数。明确不存在时可按已记录规则转换为 0；“不使用”只记录使用习惯，不据此判断持有状态。
- `energy_services` 分开保存服务、能源、技术、设备类别引用及主要/辅助用途；不能将几项服务直接计成几台设备。
- `usage_habits` 使用 `subject_type`、`subject_id`、`behavior`、`value`、`unit`、`time_scope`，明确适用对象和时间范围。
- 舒适温度保存在偏好中，不转成实测温度、设备设定值或允许调节范围。

电动车等已提取信息不在这六类设备片段中；完整已提取画像仍应读取全量观测或完整日示例。完整设备目录、字段类型及全量映射尚未冻结。

## 两条消息示例

[SGSC 消息](../examples/sft_format/sgsc_messages.json)和[iFlex 消息](../examples/sft_format/iflex_messages.json)结构相同：

| 位置 | 实际内容 |
|---|---|
| `messages[0]` / `system` | 固定任务、单位及输出格式说明。 |
| `messages[1]` / `user` | 一句任务说明，换行后为含 `profile`、`history`、`context` 的 JSON。 |
| `messages[2]` / `assistant` | `{"energy_kwh":[...]}`，数值逐项来自对应完整日示例。 |
| `metadata` | 源文件路径与哈希、源家庭、点数、状态及限制；不发送给模型。 |

两例均使用预测起点前连续七天，答案覆盖之后 24 小时。SGSC 为 336 个历史点、48 个目标点，间隔 30 分钟；iFlex 为 168 个历史点、24 个目标点，间隔 60 分钟。单位均为区间电量 kWh，时间坐标沿用源定义，未推断 UTC 偏移。

在仓库根目录重新生成并检查这两例：

```bash
python3 scripts/build_sft_format_examples.py
```

脚本核对同户关联、来源哈希、连续历史边界、目标时长、点数、序列原值与 JSON 读回结果。它只转换现有例子；不补造画像、不生成设备轨迹、不运行训练。`desired_loss_scope` 只记录预期监督位置，尚未由训练器实现损失掩码。

## 全量文件的构造与检查

```bash
python3 scripts/verify_release.py
python3 scripts/audit_extraction_completeness.py
```

需要原始来源文件的重建命令见 [画像更新说明](PROFILE_UPDATE_20260908.md)。仅用公开文件可以检查文件哈希、数量、表格与 JSON 一致性等；附加源路径才能执行原始记录比对。

全量 SGSC 尚未按零点边界重新切分七天历史，也未将目标扩成全天。逐字段采集时点及事件通知在预测前是否可得尚未全部确认。两个格式示例通过检查，不代表这些全量构造检查已完成。
