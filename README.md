# 影鉴 Aegis Review

方向 A「智能数字媒体内容审核系统」的五人协作项目。

> 当前阶段：**组长核心已完成**。仓库可以启动并提供健康检查，已经实现安全任务目录、持久化状态机、单 worker 异步编排、失败恢复、人工改判核心、产物白名单和统计服务。任务 HTTP 路由、真实 CV 分析管线、完整三栏工作台和最终验收资料仍由对应成员分支完成。

## 当前可运行内容

- Flask 应用工厂和 `app.py` 入口；
- `GET /api/health`；
- 流式 `AssetInput`、持久化 `JobRecord` 和报告 Schema；
- 安全任务 ID、staging 目录、原子 JSON 与路径边界；
- `created → queued → running → completed/failed` 持久化状态机；
- 单 worker 后台执行、任务锁、失败重试与启动恢复；
- 人工改判、报告读取、产物白名单和任务统计服务；
- `pass | review | reject` 审核枚举；
- 默认审核规则和报告 Schema；
- Docker 与 Conda 隔离环境；
- 五人任务书、提示词和 Git 协作规则。

## 组长核心集成接口

应用工厂只创建一个任务服务，后端从以下位置获取：

```python
service = app.extensions["aegis_job_service"]
```

后端不得在 `api.py` 中创建第二个 `JobService`、线程池或状态机。公开服务方法与返回结构见 [系统设计](docs/SYSTEM_DESIGN.md) 和 [API 契约](docs/API.md)。

CV 分支合入前，应用使用 `UnavailableAnalyzer`。调用分析会留下状态为 `failed`、错误为“CV 分析组件尚未就绪。”的可重试任务，不会阻止 Flask 启动。CV 集成时由组长把真实 Detector 绑定到 `analyze_asset`，再作为四参数 runner 注入服务。

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

当前尚未包含 `models/aegis_game_best.pt`，因此健康检查中的 `model_ready` 应为 `false`。CV 分支合入最终权重后应变为 `true`。即使模型文件存在，真实分析仍需完成 Detector 与 pipeline 的集成绑定。

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

## 环境与重启说明

- Docker 是唯一正式验收路径，Conda 只作为宿主机开发备用。
- Apple Silicon 使用 ARM64 容器和 CPU 版 PyTorch；首次构建下载依赖时间较长。
- Compose 只把 `outputs` 挂载为可写目录，把 `models` 挂载为只读目录。
- Flask 必须保持单进程，`app.py` 即使启用 `--debug` 也禁用 reloader，避免创建两个线程池。
- 服务重启时，磁盘中遗留的 `queued/running` 会标记为 `failed` 并保留输入文件，可重新分析。
- Windows 宿主机仍使用文件级 `flush + fsync + os.replace` 原子写入；由于
  Windows 不支持打开目录文件描述符，只跳过父目录 fsync。Docker/Linux 与
  macOS 继续执行父目录 fsync。
- Ultralytics 配置写入 `/tmp/ultralytics`，不污染仓库或宿主机用户目录。

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

## 当前限制

- 只有健康检查是当前可调用的 HTTP 业务接口，其余路由由后端成员实现；组长核心可通过 Python 服务接口测试。
- 尚未迁移数据集和模型，不能进行真实 YOLO 推理。
- 当前页面是契约阶段说明页，不是最终审核工作台。
- 五名成员姓名和 GitHub 账号已登记，学号仍待补充。
- 最终演示、截图、两个真实 Bug、贡献表和 `李_A_day08` 交付包必须等待成员功能合入并完成真实验收后生成。
