# Day08 方向 A 提交前核验

> 对照文件：`day08_CV综合项目实战_任务书.md`
> 核验日期：2026-07-18
> 核验人：李佳铭

## 方向 A 必须功能

| 任务书要求 | 项目实现与证据 |
|---|---|
| 上传图片或视频 | `POST /api/jobs`，支持 jpg/jpeg/png/mp4/mov |
| YOLO 检测图片或视频采样帧 | 自训练 `aegis_game_best.pt` + OpenCV 采样 |
| 类别、置信度、边界框 | 报告 JSON 与 `detections.csv` |
| 配置化审核规则 | `risk_classes` 和三档阈值 |
| 通过/待复核/不通过 | 三个真实图片任务与截图 |
| 至少一张证据帧 | `outputs/<job_id>/evidence/frame_*.jpg` |
| 页面展示素材、检测、结论、证据 | 三栏工作台与 16 张截图 |
| 人工修改并写回 JSON | 真实改判任务 `20260718_122854_4fc3df62` |
| 报告可重新读取 | 历史任务、报告 API、包内真实 `outputs/` |
| 明确异常提示 | 格式、空文件、模型缺失、任务失败测试 |

## 共享工程要求

- 状态机：`created → queued → running → completed/failed`。
- 上传先返回 Job ID，分析在单 worker 后台执行，页面轮询。
- 每个任务保留 `job.json`；失败任务同样留档。
- Flask、原生 HTML/CSS/JS、OpenCV、YOLO、FFmpeg、JSON 与本地文件均实际使用。
- API 成功统一 `ok: true`，错误统一 `ok: false` 与中文说明。
- 运行中任务禁止删除，非法路径和符号链接不能越界。

## 测试与协作

- 正常矩阵 N1–N8，异常矩阵 A1–A12。
- 4 个真实 Bug 含复现、根因、修复提交和回归结果。
- 五位成员姓名、学号、GitHub、邮箱和提交记录完整。
- 宿主机全量测试 0 failed；Docker 全量测试 0 failed。
- GitHub 功能 PR 和最终 QA PR 均使用普通 merge commit。

## 最终 ZIP 结构

`李_A_day08.zip` 只解压出一个目录：

```text
李_A_day08/
├── app.py
├── requirements.txt
├── environment.yml
├── Dockerfile
├── compose.yaml
├── aegis_review/
├── static/
├── templates/
├── tests/
├── models/aegis_game_best.pt
├── dataset/
├── training_evidence/
├── outputs/                    # 一组真实图片 + 一组真实视频
├── screenshots/                # 15 张门禁 + 1 张移动端
├── docs/
└── demo/demo_script.md
```

解压后执行 README 的课程 `yolo` 环境命令或 Docker 命令即可启动。包内真实
`outputs/` 使用应用原生运行目录，因此页面启动后可直接重新打开处理结果。

## 隐私与完整性

- 无 API Key、密码或个人设备绝对路径。
- 不包含 `training_runs/`、缓存、`last.pt` 或运行日志。
- 最终权重、训练指标、真实结果、截图和演示稿均包含。
- 发布脚本要求八项门禁全部通过才允许生成，并固定 ZIP 时间戳和文件顺序；
  两次独立构建必须字节一致，CRC 必须正常。
