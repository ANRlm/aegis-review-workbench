# 影鉴模型说明（CV）

## 数据来源

本仓库 `dataset/` 来自组长核验迁移包 `cv-source-day05-day06.zip`
（SHA-256 `9aa525b58ce55d7c718e3bb856b32930dc866c15afe15c6fc5fdef8ec22cf4a9`）。

- Day05：原创程序化游戏场景 YOLO 标注（非真实照片采集）
- Day06：类别设计说明与类别顺序核对

校验摘要：

| 项目 | 值 |
| --- | --- |
| train 图片/标签 | 96 / 96 |
| val 图片/标签 | 24 / 24 |
| 类别顺序 | `player`, `enemy`, `energy_orb`, `treasure_chest`, `health_potion` |
| 标签实例 | player=85, enemy=80, energy_orb=90, treasure_chest=86, health_potion=74 |

`dataset/data.yaml` 使用项目相对路径 `path: dataset`，不包含 `/workspace` 或其他机器绝对路径。

## 初始化权重

- 文件：`models/yolo11n.pt`
- 来源：Day05 迁移包中的官方 YOLO11n 初始化权重
- SHA-256：`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`
- 用途：仅作为 Day08 重新训练起点，**不是**最终审核模型

## 训练参数

在 Conda 环境 `aegis-review` 中执行：

```bash
conda activate aegis-review
python scripts/train_model.py --epochs 30 --device cpu
```

固定参数：

| 参数 | 值 |
| --- | ---: |
| epochs | 30 |
| imgsz | 640 |
| batch | 2 |
| device | cpu |
| seed | 20260718 |
| Ultralytics | 8.4.92 |
| 输出目录 | `training_runs/day08_game_audit`（不提交） |

本次实测：

- 耗时：约 **902.07 秒**（约 0.247 小时）
- 机器：Windows，AMD Ryzen 7 7840H，CPU 训练
- Torch：`2.13.0+cpu`

## 最终权重与指标

- 最终权重：`models/aegis_game_best.pt`
- SHA-256：`fcc842e69565037681c5a7d8f6a75881217eb66c246bdd4d88330d6d0b1dd957`
- 校验文件：`training_evidence/aegis_game_best.sha256`
- 指标 CSV：`training_evidence/results.csv`
- 曲线：`training_evidence/results.png`、`BoxPR_curve.png`、`confusion_matrix.png`
- 摘要：`training_evidence/train_summary.json`

验证集（24 图 / 85 实例）最终指标：

| 指标 | 值 |
| --- | ---: |
| Precision | 0.9966 |
| Recall | 1.0000 |
| mAP50 | 0.9950 |
| mAP50-95 | 0.9926 |

按类 mAP50-95（best 权重复验）：player 0.983，enemy/energy_orb/treasure_chest/health_potion 均为 0.995。

## 推理与审核管线

固定入口：

```python
from functools import partial
from aegis_review.cv import UltralyticsDetector, analyze_asset

detector = UltralyticsDetector("models/aegis_game_best.pt")
runner = partial(analyze_asset, detector=detector)
# runner(input_path, evidence_dir, result_dir, settings) -> AnalysisReport
```

规则顺序：

1. 任一 `enemy` 置信度 `>= 0.60` → `reject`
2. 最大 `enemy` 置信度位于 `[0.35, 0.60)` → `review`
3. 低置信度风险帧比例严格位于 `(0.20, 0.80)` → `review`
4. 其余 → `pass`

视频按 `sample_interval_seconds` 时间采样，最多 `max_sample_frames`（默认 120）。无检测时仍保存第一帧代表证据。

## 限制

- 数据为程序化游戏场景，泛化到真实照片/异风格素材有限。
- 默认在 CPU 上训练与推理，长视频在 120 帧上限内仍可能较慢。
- 健康检查只确认 `models/aegis_game_best.pt` 是否存在；真正分析还需服务层绑定 `analyze_asset`。
- 禁止在 Flask 启动时训练；`training_runs/`、`last.pt`、缓存与训练批次大图不进入 Git。

## 重训命令

```bash
conda activate aegis-review
python scripts/validate_dataset.py
python scripts/train_model.py --epochs 30 --device cpu
# 可选：Get-FileHash models/aegis_game_best.pt -Algorithm SHA256
```
