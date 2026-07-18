# 影鉴 Aegis Review 测试报告

> 生成：2026-07-18（第四次更新）
> 角色：测试与交付工程师 — 朱可心 (xin-rabbit)
> 基线：feature/qa-delivery 普通 merge origin/main（含组长核心 PR #2）
> 快照：9ad94cb (朱可心 10 commits)

## Docker 全量测试

```text
docker compose build
docker compose run --rm app pytest -q --tb=short
→ 118 passed, 30 skipped, 0 failed in 1.64s

python -m py_compile app.py scripts/package_release.py → exit=0
node --check static/app.js → exit=0
```

## 跳过审计 (30)

| 原因 | 数量 | 合理 |
|------|------|------|
| 后端 API 未合并 | 22 | 是 |
| 容器无 git (hygiene 宿主机已验证) | 7 | 是 |
| outputs/ 无真实目录 | 1 | 是 |

全部 30 skip = 真实阻塞，无虚假 skip。

## 组长核心 (验证通过)

| 测试组 | 内容 | 结果 |
|--------|------|------|
| test_storage.py | 原子 JSON、非法 ID、symbolic 防护 | ✅ |
| test_service.py | 状态机、恢复、删除、重试、改判、白名单 | ✅ |
| test_app_factory.py | 应用工厂注册 | ✅ |
| test_domain.py | JobRecord、AuditSettings | ✅ |
| test_contract.py | health、404 包络 | ✅ |
| test_scaffold_files.py | 骨架完整性 | ✅ |

## QA 测试 (A / D 系列)

| ID | 测试 | 状态 |
|----|------|------|
| A4 | 阈值顺序 (domain) | ✅ |
| A9 | 非法 job ID (storage/service) | ✅ |
| A10 | ../ 路径防护 (storage) | ✅ |
| **A11a** | **resolve_artifact 拒绝符号链接** | ✅ ArtifactNotFoundError 真实抛出 |
| A11b | HTTP artifact route | 阻塞 |
| **A12** | **重启恢复 (JobService 直接)** | ✅ queued+running → failed |
| D7 | release 模块 (sys.executable 绑定) | ✅ |
| **D8** | **确定性 ZIP 两目录 SHA-256 一致** | ✅ |
| D9a‑e | hygiene 回归 (tmp git) | 容器 skip (宿主机有 git) |
| D10a‑c | completed job 门禁校验 | ✅ |
| D11a‑c | Bug/截图 gate 解析 | ✅ |
| D12a | validation_outputs 选择逻辑 | ✅ |

## 阻塞项

- 后端 API 未合并 — 无 job CRUD 路由
- CV pipeline 未合并 — 无推理
- 前端工作台未合并 — 无页面
- 模型缺失 — model_ready=false
- 2 个真实 Bug — 联调未开始
- 截图 — 前端未合并
- 李_A_day08.zip — 闸门未全过

## 总结论：阻塞 (后端/CV/前端 未合并)
