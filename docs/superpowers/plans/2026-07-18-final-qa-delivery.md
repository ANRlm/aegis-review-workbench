# 影鉴 Aegis Review 最终 QA 与交付实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task.
> 功能修复使用 `superpowers:test-driven-development`，完成前使用
> `superpowers:verification-before-completion`。

**目标：** 由本机组长接管剩余 QA 与交付工作，修复验收阻塞，生成真实
图片/视频结果、截图、Bug 记录和确定性 `李_A_day08.zip`，再普通合并最终
QA PR。

**架构：** 保留 Flask、单线程 `JobService`、YOLO、JSON 文件存储和 Docker
正式验收路径。测试通过注入真实或确定性 Detector 消除过时跳过与竞态；
正式证据来自 Docker 服务和真实模型。

**技术栈：** Python 3.11、Flask 3.1.2、Ultralytics 8.4.92、OpenCV、
FFmpeg、原生 HTML/CSS/JavaScript、pytest、Docker Compose。

## 全局约束

- 工作分支为 `leader/qa-integration`，推送至 `feature/qa-delivery`。
- 新增提交使用 `cnhyk <nai.ying.cnhyk@gmail.com>`。
- 保留朱可心已有的真实提交，不重写作者，不伪造贡献。
- 禁止 force push、rebase、squash；最终使用普通 merge commit。
- `outputs/` 和最终 ZIP 不提交；截图、测试与文档提交。
- Docker 是正式验收路径，Conda 是宿主机回归路径。

## 任务

### 1. 成员信息和计划

- 补齐五人的姓名、学号、GitHub、邮箱与分支映射。
- 记录成员已授权将学号写入公开课程仓库。
- 保存本计划并以文档提交发布。

### 2. 集成验收测试

- `make_app()` 默认使用 `testing=True`，避免宿主或容器环境变量污染。
- 增加真实模型、静态 Detector、阻塞 Analyzer 和托管应用辅助接口。
- `poll()` 在任务进入 `failed` 后立即报告，而非等待超时。
- N1/N3 使用真实模型；三档规则和其余业务使用确定性 Detector。
- 重复分析与运行中删除使用阻塞 Analyzer 消除竞态。
- 删除后端、CV 和 Detector 尚未合并的过时跳过。

验证：

```bash
conda run -n aegis-review pytest -q tests/test_acceptance.py tests/test_security.py
```

### 3. Windows 原子存储

- 测试目录 fsync 不受支持时仍能完成文件 fsync 和原子替换。
- Windows 跳过不支持的目录文件描述符 fsync；Unix/macOS 保留现有行为。

验证：

```bash
conda run -n aegis-review pytest -q tests/test_storage.py tests/test_app_factory.py
```

### 4. 发布 ZIP 校验

- 测试生产 ZIP 中的证据路径为 `evidence/frame_*.jpg`。
- 根目录伪装的 `frame_*.jpg` 不满足生产契约。
- 发布校验器按生产目录检查证据成员。

验证：

```bash
conda run -n aegis-review pytest -q tests/test_delivery.py
```

### 5. 集成回归

```bash
conda run -n aegis-review pytest -q -rs
conda run -n aegis-review python -m py_compile app.py scripts/package_release.py
node --check static/app.js
git diff --check
docker compose build
docker compose run --rm app pytest -q -rs
docker compose up -d
curl --fail http://127.0.0.1:7880/api/health
```

宿主机与 Docker 必须 0 failed。Docker 中仅允许因镜像不含 Git 产生的
hygiene 跳过，且必须在宿主机补跑。

### 6. 真实证据与截图

- 使用真实模型生成 pass、review、reject 图片任务和 completed 视频任务。
- 由李佳铭执行真实人工改判。
- 核验 JSON、CSV、ZIP、证据帧、历史、统计和下载。
- 保存门禁要求的 15 张截图，并增加 `mobile_390x844.png`。

### 7. 交付文档

- 闭环前端 `[hidden]`、运行时 Analyzer、Windows fsync、ZIP 证据路径四个
  真实 Bug。
- 更新测试报告、验收清单、贡献表、截图索引、模型与前端说明。
- 创建严格 8 分钟演示稿：45 秒背景、60 秒架构、240 秒流程、60 秒异常、
  75 秒分工总结。

### 8. 门禁和确定性归档

以下门禁必须全部通过：

```text
git_clean
hygiene_clean
pytest_pass
model_present
completed_image_job
completed_video_job
closed_bugs_ge_2
screenshots_ok
```

分别在两个目录构建 `李_A_day08.zip`，要求 SHA-256 一致且
`ZipFile.testzip()` 返回 `None`，随后在仓库根目录生成正式交付包。

### 9. GitHub 收尾

- 推送本地 HEAD 至 `feature/qa-delivery`，禁止强推。
- 创建 `test: finalize QA evidence and release delivery` PR。
- GitHub Actions 通过后使用普通 merge commit 合入 `main`。
- 在最终 `main` 上重新执行 pytest、发布门禁和归档校验。

## 完成标准

- 宿主机与 Docker 均 0 failed。
- 三档结论、视频、人工改判、历史、统计、删除和导出均有真实证据。
- 至少两个、目标四个真实闭环 Bug。
- 15 张门禁截图非空，另含 390×844 移动端截图。
- 五人公开贡献映射完整。
- 发布门禁全部通过，最终 ZIP 可重复构建且 CRC 正常。
- 最终 QA PR 使用普通 merge commit 合入 `main`。
