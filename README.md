# 影鉴 Aegis Review

方向 A「智能数字媒体内容审核系统」的五人协作项目。

> 当前阶段：**契约骨架**。仓库可以启动并提供健康检查，已经锁定领域类型、状态流转、错误响应和原子 JSON 写入。任务 API、CV 分析管线、完整三栏工作台和最终验收资料由五名成员根据 `docs/assignments/` 与 `prompts/` 分支完成。

## 当前可运行内容

- Flask 应用工厂和 `app.py` 入口；
- `GET /api/health`；
- `created → queued → running → completed/failed` 状态契约；
- `pass | review | reject` 审核枚举；
- 默认审核规则和报告 Schema；
- 原子 JSON 读写；
- Docker 与 Conda 隔离环境；
- 五人任务书、提示词和 Git 协作规则。

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

契约骨架尚未包含 `models/aegis_game_best.pt`，因此首轮健康检查中的 `model_ready` 应为 `false`。CV 分支合入最终权重后应变为 `true`。

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

- 只有健康检查是可调用的业务接口，其余路由由后端成员实现。
- 尚未迁移数据集和模型，不能进行真实 YOLO 推理。
- 当前页面是契约阶段说明页，不是最终审核工作台。
- 成员姓名、学号和 GitHub 用户名尚未提供，不能邀请协作者或生成最终姓氏命名交付包。
