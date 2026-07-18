# 影鉴 Aegis Review 最终测试报告

> 日期：2026-07-18
> 初始 QA：朱可心（xin-rabbit）
> 最终集成、真实验收与交付：李佳铭（ANRlm）
> 基线：`leader/qa-integration`，五个功能 PR 已普通合并到 `main`

## 1. 新鲜自动回归

### macOS / Conda

```text
conda run -n aegis-review pytest -q -rs
→ 373 passed in 13.59s

conda run -n aegis-review python -m py_compile app.py scripts/package_release.py
→ exit 0

node --check static/app.js
→ exit 0

git diff --check
→ exit 0
```

宿主机为 **0 failed、0 skipped**，所有集成依赖跳过均已消除。

### Docker 正式路径

```text
docker compose build
→ success

docker compose run --rm app pytest -q -rs
→ 361 passed, 9 skipped in 15.88s

docker compose up -d
curl --fail http://127.0.0.1:7880/api/health
→ {"ffmpeg_ready":true,"model_ready":true,"ok":true,
   "status":"ok","storage_ready":true}
```

Docker 的 9 个 skip 全部是容器镜像未安装 `git` 的仓库卫生临时 Git
用例；这些相同用例已在有 Git 的宿主机真实运行并通过。不存在业务依赖 skip。

## 2. 真实模型任务

以下任务均由 Docker 正式服务通过 HTTP 创建，使用
`models/aegis_game_best.pt` 和生产 `cv.pipeline`，并通过严格 completed-job
校验：

| 场景 | Job ID | 自动结论 | 最终结论 | 证据 |
|---|---|---|---|---|
| 图片 pass | `20260718_122823_c8db0377` | pass | pass | 1 帧 / 2 检测 |
| 图片 review | `20260718_122853_5f664a01` | review | review | 真实 enemy 检测 |
| 图片 reject | `20260718_122853_c15ec8f0` | reject | reject | enemy 99.8% |
| 人工改判 | `20260718_122854_4fc3df62` | reject | review | 审核人李佳铭与备注 |
| 视频 | `20260718_122855_9b72ccef` | pass | pass | 3 证据帧 / 63 检测 |
| 浏览器上传视频 | `20260718_123440_32cabc08` | pass | pass | 页面真实上传与轮询 |

视频报告包含真实采样时间戳，任务目录均包含：

```text
job.json
input/original.<ext>
evidence/frame_*.jpg
result/analysis_report.json
result/detections.csv
result/audit_package.zip
```

## 3. 导出与安全

- 实际下载 JSON：可被 `json.load` 解析。
- 实际下载 CSV：64 行（含表头），字段满足报告契约。
- 实际下载 ZIP：6 个成员，Deflate 压缩，`ZipFile.testzip() is None`。
- 路径穿越、非法 job ID、产物符号链接、运行中删除、重复分析、损坏媒体、
  空文件和超限上传均有自动测试。
- `BlockingAnalyzer` 确定性验证运行中删除与重复分析返回 HTTP 409。
- `poll()` 遇到 failed 立即失败，不再等待 30 秒。

## 4. 页面与证据

- 15 张发布门禁截图均来自真实运行页面，另有 390×844 移动端截图。
- 桌面主视口为 1366×768。
- `analysis_in_progress.png` 来自视频任务真实 running 状态，不注入伪 DOM。
- `error_unsupported.png` 来自真实 `.bmp` 上传，后端返回
  “不支持的文件扩展名: .bmp”。
- 截图与 Job ID 的逐项映射见 `docs/SCREENSHOT_INDEX.md`。

## 5. 发布交付

`scripts/package_release.py --check` 的八项门禁全部 PASS。两份独立目录构建的
`李_A_day08.zip` 字节完全一致，`ZipFile.testzip() is None`；最终包包含
106 个成员、16 张截图、真实图片 `outputs/` 和真实视频 `outputs/`。压缩包
只解出一个 `李_A_day08/` 项目目录，并额外提供 `demo/demo_script.md`。
精确 SHA-256 记录在最终 PR 与交付回执中，避免包内文档引用包自身哈希。

## 6. 结论

功能、接口、真实模型、三档审核、视频异步、人工改判、历史、统计、导出、
安全、响应式页面和确定性发布包均通过最终验收。
