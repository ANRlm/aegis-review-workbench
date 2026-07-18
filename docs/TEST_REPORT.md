# 影鉴 Aegis Review 测试报告

> 生成时间：2026-07-18（第三次更新）
> 执行角色：测试与交付工程师 — 朱可心 (xin-rabbit)
> 基线：feature/qa-delivery 普通 merge origin/main（含组长核心 PR #2）

## 测试执行环境

Docker image：`aegis-review-workbench-app:latest`（Python 3.11 slim）。

所有测试均在 Docker 容器内执行。

## 执行结果（2026-07-18 最新）

### pytest 全量

```text
106 passed, 28 skipped in ~1.9s
```

0 失败。

### python -m py_compile app.py scripts/package_release.py

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

### git shortlog -sne HEAD

```text
    11  cnhyk <nai.ying.cnhyk@gmail.com>
     7  朱可心 <2140931620@qq.com>
     2  cnhky <nai.ying.cnhyk@gmail.com>
```

### hygiene_scan（Windows 宿主机，有 git）

```text
PASS — 无密钥、无隐私绝对路径、无超大文件
```

### package_release --check（宿主机）

预期仍为非零（模型/真实任务/截图/Bug 缺失）。但 git_clean、pytest_pass、hygiene_clean 应反映真实运行结果。

## 测试矩阵

### 组长核心（已验证）

| 测试组 | 内容 | 结果 |
|--------|------|------|
| test_storage.py | 原子 JSON、非法 ID、symbolic 防护 | 25 passed |
| test_service.py | 状态机、恢复、running 删除、failed 重试 | 47 passed |
| test_app_factory.py | 应用工厂注入 | 9 passed |
| test_domain.py | JobRecord、AuditSettings | 12 passed |
| test_contract.py | health、404 包络 | 6 passed |
| test_scaffold_files.py | 骨架完整性 | 4 passed |

**组长核心合计：103 passed, 0 failed**

### QA 安全测试（A 系列）

| ID | 测试 | 状态 | 说明 |
|----|------|------|------|
| A4 | 阈值顺序 | ✅ 通过 | domain AuditSettings 校验已通过；API 校验等待后端 |
| A9 | 非法 job ID | ✅ 通过 | storage/service 层防护已通过；HTTP 路由等待后端 |
| A10 | `../` 产物路径 | ✅ 通过 | storage 层路径检查已通过；HTTP 路由等待后端 |
| A11a | 符号链接（服务层） | ✅ 通过 | storage.write/read 路径验证已通过 |
| A11b | 符号链接（HTTP） | 阻塞 | 等待后端 artifact 路由 |
| A12 | 重启恢复 | ✅ 通过 | JobService+JobStorage 直接测试（queued/running → failed） |

### QA 交付测试（D 系列）

| ID | 测试 | 状态 |
|----|------|------|
| D7 | release 模块验证 | ✅ 通过 |
| D8 | 确定性 ZIP 回归 | ✅ 通过（两次构建 SHA-256 一致） |

### 阻塞项

| ID | 状态 | 阻塞原因 |
|----|------|----------|
| N1-N8 | 阻塞 | 后端 API 未合并 |
| A1-A3, A5-A8 | 阻塞 | 后端 API + CV + 模型 |
| A11b | 阻塞 | 后端 artifact 路由 |
| 真实推理 | 阻塞 | CV + 模型 |
| 两个 Bug | 阻塞 | 联调未开始 |
| 页面截图 | 阻塞 | 前端未合并 |
| `李_A_day08.zip` | 阻塞 | package_release 闸门未全过 |

## 总结论

**状态：阻塞（后端/CV/前端 未合并）**

- ✅ 组长核心 103 passed
- ✅ Docker 全绿
- ✅ hygiene_scan 通过
- ✅ 确定性 ZIP 构建验证
- ⛔ 后端 API 未合并 — 无 job CRUD 路由
- ⛔ CV pipeline 未合并 — 无推理
- ⛔ 前端未合并 — 无工作台
- ⛔ 模型缺失
