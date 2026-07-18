# 影鉴 Aegis Review

方向 A「智能数字媒体内容审核系统」的五人协作项目。

> 当前阶段：**五人功能已集成，最终 QA 已完成**。仓库包含完整 HTTP API、
> 真实 YOLO 分析管线、三栏审核工作台、安全持久化、人工改判和
> JSON/CSV/ZIP 导出，并已用 Docker 正式服务生成图片、视频和截图证据。

## 已实现内容

- Flask 应用工厂和 `app.py` 入口；
- 健康、任务 CRUD、异步分析、报告、产物、改判与统计 API；
- 流式 `AssetInput`、持久化 `JobRecord` 和报告 Schema；
- 安全任务 ID、staging 目录、原子 JSON 与路径边界；
- `created → queued → running → completed/failed` 持久化状态机；
- 单 worker 后台执行、任务锁、失败重试与启动恢复；
- 人工改判、报告读取、产物白名单和任务统计服务；
- `pass | review | reject` 审核枚举；
- 五类 YOLO 检测、图片/视频采样、三档审核规则和报告 Schema；
- 暖白/石墨/青绿三栏工作台、历史重开、轮询与响应式布局；
- 真实图片/视频证据、15 张门禁截图与移动端截图；
- Docker 与 Conda 隔离环境；
- 五人任务书、提示词和 Git 协作规则。

## 组长核心集成接口

应用工厂只创建一个任务服务，后端从以下位置获取：

```python
service = app.extensions["aegis_job_service"]
```

后端不得在 `api.py` 中创建第二个 `JobService`、线程池或状态机。公开服务方法与返回结构见 [系统设计](docs/SYSTEM_DESIGN.md) 和 [API 契约](docs/API.md)。

默认应用工厂会在最终权重存在时将真实 Detector 绑定到 `analyze_asset`；
权重缺失时才使用 `UnavailableAnalyzer`。测试仍可通过 `create_app(...,
job_service=fake_service)` 注入确定性服务。

## 项目目标

```text
上传图片或视频
  → 创建任务
  → 异步 YOLO 分析
  → 展示证据与三档结论
  → 人工改判
  → 历史重开
  → 导出 JSON / CSV / ZIP
```

最终系统使用 Python 3.11、Flask 3.1.2、OpenCV、Ultralytics YOLO 8.4.92、FFmpeg、原生 HTML/CSS/JavaScript，以及本地目录和 JSON。

## Docker 启动

正式验收统一使用 Docker。先启动 Docker Desktop 或 OrbStack：

```bash
cd aegis-review-workbench
docker compose build
docker compose up -d
curl http://127.0.0.1:7880/api/health
```

浏览器访问 `http://127.0.0.1:7880`。

仓库已包含 `models/aegis_game_best.pt`。正常挂载后健康检查中的
`model_ready`、`ffmpeg_ready` 和 `storage_ready` 都应为 `true`；若首次启动
需要加载模型，请等待容器 health 变为 healthy 后再上传。

停止服务：

```bash
docker compose down
```

## Conda 本地开发

宿主机开发不得使用全局 Python：

```bash
cd aegis-review-workbench
conda env create -f environment.yml
conda activate aegis-review
python app.py --host 127.0.0.1 --port 7880
```

## 验证

```bash
conda activate aegis-review
pytest -q
python -m py_compile app.py
node --check static/app.js
```

容器门禁：

```bash
docker compose run --rm app pytest -q
docker compose run --rm app python -m py_compile app.py
docker compose run --rm app node --check static/app.js
```

最终发布门禁：

```bash
conda run -n aegis-review python scripts/package_release.py --check
```

## 环境与重启说明

- Docker 是唯一正式验收路径，Conda 只作为宿主机开发备用。
- Apple Silicon 使用 ARM64 容器和 CPU 版 PyTorch；首次构建下载依赖时间较长。
- Apple Silicon 首次真实推理会加载权重，短暂等待属于正常现象；课程验收统一使用 CPU。
- Compose 只把 `outputs` 挂载为可写目录，把 `models` 挂载为只读目录。
- Flask 必须保持单进程，`app.py` 即使启用 `--debug` 也禁用 reloader，避免创建两个线程池。
- 服务重启时，磁盘中遗留的 `queued/running` 会标记为 `failed` 并保留输入文件，可重新分析。
- Windows 宿主机仍使用文件级 `flush + fsync + os.replace` 原子写入；由于
  Windows 不支持打开目录文件描述符，只跳过父目录 fsync。Docker/Linux 与
  macOS 继续执行父目录 fsync。
- Ultralytics 配置写入 `/tmp/ultralytics`，不污染仓库或宿主机用户目录。
- 真实任务、训练运行目录和最终 ZIP 不进入 Git；最终 ZIP 由发布脚本确定性生成。

## 协作入口

- 产品要求：[docs/PRD.md](docs/PRD.md)
- 系统设计：[docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md)
- API 契约：[docs/API.md](docs/API.md)
- Git 工作流：[docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md)
- 成员表：[docs/TEAM_ROSTER.md](docs/TEAM_ROSTER.md)
- 个人任务书：[docs/assignments](docs/assignments)
- 编码助手提示词：[prompts](prompts)

四名成员固定分支：

```text
feature/leader-core
feature/backend-api
feature/cv-pipeline
feature/frontend-workbench
feature/qa-delivery
```

使用普通 merge commit 合入，禁止 squash、rebase 和伪造 Git 作者。最终通过以下命令核验贡献：

```bash
git shortlog -sne --all
git log --graph --oneline --decorate --all
```

## 目录

```text
aegis-review-workbench/
├── aegis_review/        # Flask、领域与后续业务模块
├── dataset/             # CV 成员迁移的 96/24 YOLO 数据
├── models/              # 最终自训练权重
├── outputs/             # 运行时任务目录，不提交
├── static/              # 前端成员独占
├── templates/           # 前端成员独占
├── tests/               # 各角色按文件边界追加测试
├── docs/                # 契约与验收资料
├── prompts/             # 五人提示词
├── Dockerfile
├── compose.yaml
├── environment.yml
└── app.py
```

## 已知边界

- 训练数据是 96/24 的程序化五类游戏场景，不能代表通用真实世界审核能力。
- 服务采用单进程、单 worker；不支持多 Gunicorn worker、分布式队列或批量图片。
- 视频最多采样 120 帧，长视频按配置间隔抽样而不是逐帧处理。
- 最终证据、Bug、贡献与演示材料分别见
  [测试报告](docs/TEST_REPORT.md)、[Bug 记录](docs/BUG_RECORD.md)、
  [贡献核验](docs/CONTRIBUTIONS.md) 和 [8 分钟演示稿](docs/DEMO_SCRIPT.md)。
