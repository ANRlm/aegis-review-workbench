# 01 组长任务书（40%）

## 目标

负责产品、系统骨架、持久化任务核心、环境隔离和最终集成。组长的产出必须既有代码也有文档和可复现验收证据，不能只承担协调。

## 前置阅读

1. `README.md`
2. `docs/PRD.md`
3. `docs/SYSTEM_DESIGN.md`
4. `docs/API.md`
5. `docs/GIT_WORKFLOW.md`
6. `tests/test_contract.py`

## 独占路径

- `app.py`
- `aegis_review/__init__.py`（应用工厂和服务生命周期注入）
- `aegis_review/config.py`
- `aegis_review/domain.py`
- `aegis_review/storage.py`
- `aegis_review/service.py`
- `Dockerfile`、`compose.yaml`、`environment.yml`、`requirements.txt`
- `README.md`
- `docs/PRD.md`、`docs/SYSTEM_DESIGN.md`、`docs/GIT_WORKFLOW.md`
- `demo/`

契约骨架已经创建。后续若其他成员需要改变这些文件，必须先由组长确认接口影响。

## 工作包

### L1：仓库与协作基线

- 补齐 `docs/TEAM_ROSTER.md` 的五人真实信息；
- 邀请四名 GitHub 协作者；
- 确认每人 Git 邮箱属于本人 GitHub；
- 保留 merge commit，关闭 squash/rebase 合并；
- 建立 PR 模板，要求列出修改、测试、截图和契约影响。

验收：五人能够从相同 `main` 创建固定分支，`git shortlog -sne --all` 能区分真实作者。

### L2：任务目录与原子存储

- 实现合法任务 ID 生成和校验；
- 创建 `input/evidence/result` 目录；
- 实现 `job.json` 创建、读取、列表和安全删除；
- 每个任务使用独立锁；
- 删除前验证真实路径位于 `outputs`；
- 测试 JSON 原子替换、非法 ID、路径越界和运行中删除。

验收：服务异常不能留下半个 JSON；非法目录不被读取或删除。

### L3：状态机与后台执行

- 创建任务后保持 `created`；
- 分析请求先落盘 `queued` 再提交线程池；
- 单 worker 写入 `running/started_at`；
- 成功写 `completed/completed_at/result_file`；
- 异常写 `failed/completed_at/error`；
- 启动时把遗留 `queued/running` 任务改为 `failed`；
- `failed` 允许清理旧结果后重新分析；
- 通过依赖注入调用 CV 成员提供的 pipeline。

验收：状态不能跳跃；失败任务总有可读错误；浏览器请求不会等待模型推理。

### L4：环境隔离

- 固定 Python/Flask/Ultralytics 版本；
- Docker 内确认 FFmpeg、Node、中文字体、模型路径和可写输出；
- Conda 环境只作为本地备用；
- Ultralytics 配置写到容器或项目临时目录；
- Compose 只把 `outputs` 设为可写、`models` 设为只读；
- 记录 Apple Silicon 和 CPU 推理注意事项。

验收：README 的 Docker 命令从干净环境可运行；容器测试通过。

### L5：集成与展示

- 按 CV → 后端 → 前端 → QA 顺序主持合并；
- 每次合并后运行全部测试；
- 契约问题先改文档和契约测试，再让责任成员修改；
- 完成 8 分钟演示稿：背景 45 秒、架构 60 秒、完整流程 4 分钟、异常 60 秒、分工与总结 75 秒；
- 整理系统架构图、最终验收清单和提交贡献表。

验收：一条命令启动，完整路径和一个异常路径可以现场复现。

## 建议提交

1. `feat: add durable job storage and safe task paths`
2. `feat: implement persistent job lifecycle`
3. `test: cover recovery and status transition boundaries`
4. `build: complete Docker and Conda isolation`
5. `docs: finalize architecture and startup guide`
6. `fix: resolve verified integration issue`
7. `docs: add acceptance checklist and demo script`

只有真实出现并验证的集成问题才能使用 `fix:`。

## 最终自检

```bash
pytest -q
python -m py_compile app.py
node --check static/app.js
docker compose build
docker compose run --rm app pytest -q
docker compose up -d
curl --fail http://127.0.0.1:7880/api/health
git diff --check
git shortlog -sne --all
```

## 禁止事项

- 不冒充其他成员提交；
- 不替后端编写所有路由、不替 CV 编写推理、不替前端完成页面；
- 不在启动时训练模型；
- 不引入数据库、Redis、Celery 或多进程 worker；
- 不用静态假状态和假 Bug 充当验收证据。
