# 影鉴 Aegis Review 测试报告

> 生成时间：2026-07-18（更新）
> 执行角色：测试与交付工程师 — 朱可心 (xin-rabbit)
> 基线：`feature/qa-delivery` 普通 merge `origin/main`（含组长核心 PR #2）

## 测试执行环境

- **Docker image**：`aegis-review-workbench-app:latest`（基于 Python 3.11 slim）
- **构建命令**：`docker compose build`
- **测试命令**（全部在容器内执行）：
  ```bash
  docker compose run --rm -v .,tests:/workspace/tests -v .,scripts:/workspace/scripts app pytest -q --tb=short
  docker compose run --rm app python -m py_compile app.py
  docker compose run --rm app node --check static/app.js
  docker compose up -d --force-recreate && docker compose exec app curl -s http://127.0.0.1:7880/api/health
  ```

## 执行结果（2026-07-18 最新）

### pytest 全量

```text
106 passed, 27 skipped in 1.88s
```

0 失败。27 skip 均有明确依赖原因（见矩阵）。

### python -m py_compile app.py

```text
exit=0
```

### node --check static/app.js

```text
exit=0
```

### pip check

```text
No broken requirements found.
```

### curl /api/health

```json
{"ffmpeg_ready":true,"model_ready":false,"ok":true,"status":"ok","storage_ready":true}
```

### git diff --check

```text
exit=0
```

### hygiene_scan（Windows 宿主机，有 git）

```text
PASS — 无密钥、无隐私绝对路径、无超大文件
```

### package_release --check（Windows 宿主机）

```text
[FAIL] closed_bugs_ge_2     (False)
[FAIL] completed_image_job  (False)
[FAIL] completed_video_job  (False)
[FAIL] git_clean            (False)  ← 工作区有未提交文档修改
[PASS] hygiene_clean        (True)
[FAIL] model_present        (False)
[FAIL] pytest_pass          (False)  ← 子进程 pytest 因 testpaths 差异失败
[FAIL] screenshots_ok       (False)
BLOCKED: 李_A_day08 cannot be generated.
```

## 测试矩阵

### 组长核心（已合入，真实执行）

| 测试组 | 内容 | 结果 | 证据 |
|--------|------|------|------|
| test_storage.py | 原子 JSON、非法 ID、目录创建、完整性校验、symbolic 防护、并发写 | ✅ 全部通过 | 25 passed |
| test_service.py | 状态机、恢复、queued/running 标记 failed、running 删除冲突、failed 重试、人工改判、产物白名单、统计、UnavailableAnalyzer | ✅ 全部通过 | 47 passed |
| test_app_factory.py | 应用工厂注入、配置绑定、测试模式 | ✅ 全部通过 | 9 passed |
| test_domain.py | JobRecord 序列化、AuditSettings 校验、AnalysisReport contract | ✅ 全部通过 | 12 passed |
| test_contract.py | health、404 包络、domain enum、原子存储 | ✅ 全部通过 | 6 passed |
| test_scaffold_files.py | 骨架文件完整性 | ✅ 全部通过 | 4 passed |

**组长核心总计：103 passed, 0 failed**

### QA 独占安全测试（A 系列）

| ID | 测试 | 状态 | 说明 |
|----|------|------|------|
| A4 | 阈值顺序错误 | ✅ 通过 | domain 层 + API 层均已验证 |
| A9 | 非法任务 ID | ✅ 通过 | 404 + 错误包络正确 |
| A10 | `../` 产物路径 | ✅ 通过 | 404 拒绝 |
| A11 | 符号链接逃逸 | ✅ 通过 | leader 存储防护已覆盖 |
| A12 | 重启恢复 | ✅ 通过 | leader 已实现 recovery |

### 正常路径（N1–N8）— 阻塞

| ID | 测试 | 状态 | 阻塞原因 |
|----|------|------|----------|
| N1 | 图片全流程 | 阻塞 | 后端 API 未合入 |
| N2a/b/c | 三档审核 | 阻塞 | CV + 后端 + 模型 |
| N3 | 视频异步 | 阻塞 | CV + 后端 + 模型 |
| N4 | 人工改判 | 阻塞 | 后端 API（改判服务已由 leader 实现，路由等待后端） |
| N5 | 历史重开 | 阻塞 | 后端 API（storage 已由 leader 实现） |
| N6 | 产物下载 | 阻塞 | 后端 API + 真实产物 |
| N7 | 删除 | 阻塞 | 后端 API |
| N8 | 统计 | 阻塞 | 后端 API |

### 异常路径（A1–A3, A5–A8）— 阻塞

| ID | 测试 | 状态 | 阻塞原因 |
|----|------|------|----------|
| A1 | 错误扩展名 | 阻塞 | 后端 API |
| A2 | 空文件 | 阻塞 | 后端 API |
| A3a/b | 损坏媒体 | 阻塞 | 后端 API |
| A5 | 空审核人 | 阻塞 | 后端 API |
| A6 | 重复分析 | 阻塞 | 后端 API |
| A7 | 模型缺失 | 阻塞 | 后端 API |
| A8 | 运行中删除 | 阻塞 | 后端 API + CV |

### 交付物验证

| ID | 测试 | 状态 |
|----|------|------|
| D1 | 产物目录骨架 | 跳过（无真实 outputs） |
| D2 | 仓库卫生（宿主机） | ✅ 通过 |
| D3 | 大文件检查 | 跳过（容器无 git） |
| D4 | outputs 不提交 | 跳过（容器无 git） |
| D5/D6 | compose/Dockerfile | ✅ 通过 |
| D7 | release 模块 | ✅ 通过（姓氏=李, gate 语义正确） |

### 永远可运行（无需任何依赖）

| 测试 | 状态 |
|------|------|
| health 真实性（model_ready 非硬编码） | ✅ |
| 404 错误包络格式 | ✅ |
| domain AuditSettings 阈值校验 | ✅ |
| JSON/CSV/ZIP validator 自检 | ✅ |

## 跳过审计

| 跳过原因 | 数量 | 是否合理 |
|----------|------|----------|
| 后端 API 未合并 | 23 | ✅ 合理 — 无路由 |
| 容器无 git | 3 | ✅ 合理 — 宿主机已补跑 hygiene |
| 无 real outputs | 1 | ✅ 合理 — 真实任务不存在 |
| **合计** | **27** | **全部合理，无虚 skip** |

## 总结论

**状态：阻塞 ⛔（后端/CV/前端 未合并）**

已完成的真实工作：
- ✅ Docker 构建 + 启动 + health
- ✅ 组长核心全量测试（103 passed）
- ✅ QA 安全/交付测试（组长核心相关全部通过）
- ✅ py_compile + node --check
- ✅ 仓库卫生扫描
- ✅ 交付脚本模块验证
- ✅ pip check

阻塞项：
1. CV pipeline 未合并 — 无 YOLO 推理
2. 后端 API 未合并 — 无 job CRUD 路由
3. 前端工作台未合并 — 无审核工作台
4. 模型文件缺失 — model_ready=false
5. 无真实推理产物 — 无法验证 JSON/CSV/ZIP 实际内容
6. 无真实 Bug — 联调未开始，不编造
7. 页面截图不可得
8. 最终包 `李_A_day08` 不生成
9. requirements.txt torch 无 win32 marker（契约疑点，QA 不越权修改）
