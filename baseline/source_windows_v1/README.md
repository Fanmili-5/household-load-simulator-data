# v1 构造所用的固定窗口输入

`windows.jsonl.gz` 保存经原读数核验的同户七天历史、全天答案、活动条件与源记录关联。它是抽取后的窗口文件，不是未经处理的原始 CSV。没有画像；家庭画像从仓库根目录的已发布观测重新映射。

`windows.jsonl.report.json` 保存源读数文件哈希、排除窗口和本文件校验值。窗口文件哈希同时写入 `baseline/v1/manifest.json`。

仅使用本仓库即可重新生成 v1 的全部 17 个数据/格式工件与版本清单：

```bash
python3 scripts/build_baseline.py --window-cache baseline/source_windows_v1/windows.jsonl.gz --output outputs/rebuilt_baseline
python3 scripts/verify_baseline.py --root outputs/rebuilt_baseline
```

若需要从原始 CSV 重新抽取窗口，使用 `scripts/baseline_windows.py --pipeline-root /path/to/load_response_pipeline`；原文件名和哈希在报告中。SGSC 与 iFlex 的内容分别沿用仓库 `DATA_LICENSES.md` 中注明的数据许可。
