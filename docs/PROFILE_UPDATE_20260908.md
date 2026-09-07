# 2026-09-08 家庭画像更新

本次修改了实际数据文件，不只是补充说明。SGSC 16,342 条记录和 iFlex 2,071 条记录都已加入扩展画像；候选成员、历史读数、目标电量、活动条件和已有参考估计保持原值。

后续逐列复核又发现汇总表遗漏完整设备列表，以及部分筛选回答尚未进入画像，现已修正并重建两份数据。具体差异、仍暂存追溯区的字段及核对范围见 [提取复核](EXTRACTION_AUDIT_20260908.md)。

## SGSC

按原始家庭表的准确记录位置关联 2,078 户，逐条确认户号及整行内容与原清洗批次的来源记录一致。补入节电努力程度、互联网接入、住房和燃气用途等整理字段，保留白天在家及干衣机使用习惯。

每条观测的 `metadata.profile_provenance.raw_answers` 保留原家庭记录全部 46 列（包括户号和管理字段）。退出原因、服务状态、活动后的日期及假定用电水平等仍放在追溯区，不作为新增预测特征。家庭人数、年龄、收入和完整设备清单等未采集信息仍为未知。

## iFlex

按同一匿名 ID 关联 Survey 1 的 314 户，保留全部 96 列原回答，并加入以下整理字段：

- 家庭人数、家庭类型、年龄构成、生活状态、教育程度、收入区间及问卷性别字段。
- 住房所有权、面积、建造年代、节能改造、出租单元和合住情况。
- 舒适温度、夜间或无人时降温、少用房间温度、供暖及热水器控制、木炉使用习惯。
- 对用电和价格的关注、信息渠道及电力合同回答。
- 其他供暖方式、通风方式、车辆数量及逐车的充电地点、方式、频率、时段和控制习惯。

原问卷中 115 户有电动或插混汽车数量，已补入 99 户的 1 辆和 16 户的 2 辆；逐车信息按原题号关联，没有把第一辆车的习惯复制给第二辆。

## 异常和未知怎样处理

10 户年龄分组与家庭人数不一致，整理后的整份年龄分布设为 `null`，不猜测改数；1 户的生活状态分组人数超出家庭总人数，只将该分组数置空。收入题中 8 户不知道、15 户不愿回答，整理后的收入留空，状态分别保留。

原始值没有删除。每个已映射字段可以通过 `field_sources` 回查题号，`field_status` 区分未采集、缺失或不适用、不确定、拒答、占位符和异常，`quality_flags` 标出需要注意的整组问题。问卷中的“不使用”仍不等于“不持有”。

## 到哪里看

完整画像在 `input.profile` 的 `people`、`dwelling`、`appliances`、`preferences`、`usage_habits`、`energy_attitudes`、`energy_systems` 和 `vehicles` 中。旧 `household` 字段保留以兼容已有读取方式。

`tables/sgsc_households.csv` 和 `tables/iflex_households.csv` 每户一行，适合先检查画像；活动汇总表也展开了相同信息。数组或分组人数以 JSON 单元格保存，避免把家庭成员和车辆弄乱。所有观测样例和两个全天格式样例均已同步。

重建命令（需要本地来源文件）：

```bash
python3 scripts/build_release.py --pipeline-root /path/to/load_response_pipeline --sgsc-households /path/to/sgsc-ct-customer-household-data-revised.csv
python3 scripts/verify_release.py --pipeline-root /path/to/load_response_pipeline --sgsc-households /path/to/sgsc-ct-customer-household-data-revised.csv
```

仅使用 GitHub 文件时，运行 `python3 scripts/verify_release.py` 即可核对文件、表格与样例。源记录及字段映射核验通过，仍不等于所有画像已确认在预测前可得；逐字段采集时点尚有缺口。SGSC 全量答案也仍是原活动窗口，本次没有扩成全天或进行 SFT。
