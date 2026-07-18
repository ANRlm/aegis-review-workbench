# 影鉴 Aegis Review 测试报告

> 生成时间：2026-07-18
> 执行角色：测试与交付工程师 — 朱可心 (xin-rabbit)

## 测试执行环境

- **Docker image**：`aegis-review-workbench-app:latest`（基于 Python 3.11 slim）
- **Docker build**：2026-07-18 13:28 UTC+8, 镜像 SHA256 前 16 位 `2b54c05b0fa0f4`
- **命令**：
  ```bash
  docker compose build                          # 构建
  docker compose run --rm -v .:/workspace app pytest -q --tb=short    # 测试
  docker compose run --rm app python -m py_compile app.py             # 语法检查
  docker compose run --rm app node --check static/app.js              # JS 检查
  docker compose up -d && curl http://127.0.0.1:7880/api/health       # 健康检查
  ```

## 执行结果（新鲜，未缓存）

### pytest

```text
33 passed, 27 skipped in 0.59s
```

所有 failure = 0。27 个 skip 均有明确原因（标注在测试矩阵中）。

### python -m py_compile app.py

```text
exit=0  (无错误)
```

### node --check static/app.js

```text
exit=0  (无错误)
```

### curl /api/health

```json
{"ffmpeg_ready":true,"model_ready":false,"ok":true,"status":"ok","storage_ready":true}
```

model_ready 为 false 是真实状态（`models/aegis_game_best.pt` 未部署），非硬编码。

### git diff --check

```text
exit=0
```

### git shortlog -sne --all

```text
2  cnhyk <nai.ying.cnhyk@gmail.com>
1  cnhky <nai.ying.cnhyk@gmail.com>
```

所有提交均由组长（李佳铭 / ANRlm / cnhyk）完成。CV、后端、前端、QA 分支指向同一 commit，尚无独立提交。

### release package check

```text
package_release --check (target: 李_A_day08.zip)
[FAIL] closed_bugs_ge_2     (False)
[FAIL] completed_image_job  (False)
[FAIL] completed_video_job  (False)
[FAIL] git_clean            (git not installed)
[FAIL] hygiene_clean        (False)
[FAIL] model_present        (False)
[FAIL] pytest_pass          (False)
[FAIL] screenshots_ok       (False)
BLOCKED: 李_A_day08 cannot be generated.
```

## 测试矩阵

### 正常路径（N1–N8）

| ID | 测试 | 输入 | 命令 | 预期 | 实际 | 证据 | 状态 |
|----|------|------|------|------|------|------|------|
| N1 | 图片全流程 | `clean_scene.jpg` | POST→CREATE→analyze→poll→GET report | 201→202→completed→200 report | — | `tests/fixtures/media/health.json` | **阻塞**：后端/CV 未合并 |
| N2a | 通过结论 | `clean_scene.jpg` | POST→analyze→complete→GET report | `auto_decision: pass` | — | — | **阻塞**：后端/CV 未合并 |
| N2b | 待复核结论 | `risk_scene.jpg` | POST→analyze→complete→GET report | `auto_decision: review` | — | — | **阻塞**：CV 注入 seam 未暴露 |
| N2c | 不通过结论 | `reject_scene.jpg` | POST→analyze→complete→GET report | `auto_decision: reject` | — | — | **阻塞**：CV 注入 seam 未暴露 |
| N3 | 视频异步 | `sample_5s.mp4` | POST→analyze→poll completed | 状态变化+证据帧 | — | — | **阻塞**：后端/CV 未合并 |
| N4 | 人工改判 | `clean_scene.jpg`→完成→PATCH review | PATCH 200, auto 不变 | `final_decision: review`, `auto` 保留 | — | — | **阻塞**：后端/CV 未合并 |
| N5 | 历史重开 | `clean_scene.jpg`→创建→重启 app→GET /jobs | 任务仍在列表 | — | — | **阻塞**：后端未合并 |
| N6 | JSON/CSV/ZIP 下载 | 完成态→GET artifacts | 200, CSV 可解析, ZIP CRC 通过 | — | — | **阻塞**：后端/CV 未合并 |
| N7 | 删除 | 完成态→DELETE→GET /jobs→磁盘消失 | 200, 列表消失 | — | — | **阻塞**：后端/CV 未合并 |
| N8 | 统计 | 2 个完成+1 改判→GET /stats | 总数+review 计数 | — | — | **阻塞**：后端/CV 未合并 |

### 异常路径（A1–A12）

| ID | 测试 | 输入 | 命令 | 预期 | 实际 | 证据 | 状态 |
|----|------|------|------|------|------|------|------|
| A1 | 错误扩展名 | `.bmp` 文件 | POST /api/jobs | 400 | — | — | **阻塞**：后端未合并 |
| A2 | 空文件 | `empty.bin` (0B) | POST /api/jobs | 400 invalid_asset | — | — | **阻塞**：后端未合并 |
| A3a | 损坏图片 | `corrupt.jpg` | POST /api/jobs | 400 invalid_asset | — | — | **阻塞**：后端未合并 |
| A3b | 损坏视频 | `corrupt.mp4` | POST /api/jobs | 400 invalid_asset | — | — | **阻塞**：后端未合并 |
| A4 | 阈值顺序错误 | `review >= reject` settings | POST /api/jobs | 400 invalid_settings | domain 层 rejected ✅ | `test_audit_settings_reject_invalid_threshold_order` | domain 层 ✅ 通过；API 层阻塞：后端未合并 |
| A5 | 空审核人 | `reviewer: "   "` | PATCH review | 400 | — | — | **阻塞**：后端/CV 未合并 |
| A6 | 重复分析 | analyze×2 | POST analyze×2 | 409 | — | — | **阻塞**：后端/CV 未合并 |
| A7 | 模型缺失 | 无 `.pt` 文件 | analyze | 非 200 或 failed+error | `model_ready=false` 证实 | health JSON | **阻塞**：后端未合并（domain 层 health 实测通过） |
| A8 | 运行中删除 | 视频 analyze→DELETE | DELETE while running | 409 job_busy | — | — | **阻塞**：后端/CV 未合并 |
| A9 | 非法任务 ID | `"../../etc/passwd"` 等 | GET /api/jobs/<bad> | 404 | — | — | **阻塞**：后端未合并 |
| A10 | `../` 路径 | URL 编码遍历 | GET artifacts | 404/400 | — | — | **阻塞**：后端未合并 |
| A11 | 符号链接 | 输出目录内软链接到外部 | GET artifacts | 404/400 | — | — | **阻塞**：后端未合并（Windows 开发模式未开启） |
| A12 | 重启恢复 | 残留 running→重启→GET | status=failed | — | — | **阻塞**：后端未合并 |

### 永远可运行（健康、错误包络、领域规则）

| ID | 测试 | 状态 | 证据 |
|----|------|------|------|
| health 真实性 | model_ready 反映磁盘 | ✅ 通过 | `model_ready=false`（临时根目录无模型），非 hardcoded |
| 404 错误包络 | `GET /api/not-a-route` | ✅ 通过 | `{ok:false, error:{code, message}}` 格式正确 |
| domain 阈值校验 | `review >= reject` | ✅ 通过 | `ValueError` 正确抛出 |
| JSON 校验器 | 合法/非法 payload | ✅ 通过 | validator 自检 |
| CSV 校验器 | 缺失列检测 | ✅ 通过 | validator 自检 |
| ZIP 校验器 | 合法/损坏存档 | ✅ 通过 | validator 自检 |
| 产物目录骨架 | 扫描 outputs/ 已有任务目录 | 跳过（无） | — |
| 仓库卫生（密钥） | 扫描跟踪文件 | 跳过（容器无 git） | — |
| 仓库卫生（大文件） | 扫描跟踪文件 >5MB | 跳过（容器无 git） | — |
| outputs 不提交 | git ls-files outputs | 跳过（容器无 git） | — |
| compose 合约 | volumes 挂载检查 | ✅ 通过 | `:ro` / `:rw` 验证 |
| Dockerfile 合约 | EXPOSE/HEALTHCHECK | ✅ 通过 | 均有定义 |

## 总结论

**状态：阻塞 ⛔**

实际可运行测试 33 条全部通过（0 失败），27 条因依赖未就绪而跳过（理由标注清晰）。

以下阻塞项阻止"最终通过"：

1. **CV 管线未合并** (`feature/cv-pipeline`) — 无 YOLO 推理能力
2. **后端 API 未合并** (`feature/backend-api`) — 仅有 `GET /api/health`，无任务路由
3. **前端工作台未合并** (`feature/frontend-workbench`) — 页面为契约阶段说明页
4. **模型文件缺失** (`models/aegis_game_best.pt`) — health 端点的 `model_ready` 确认为 false
5. **数据集未迁移** (`dataset/`) — CV 工程师尚未迁移 96/24 YOLO 数据
6. **无真实推理产物** — 上述所有阻塞导致无法产出真实图片/视频推理结果
7. **无真实 Bug** — 联调尚未开始，无法产生两个有修复提交记录的 Bug（不编造）
8. **页面截图不可得** — 前端未合并，无法截取完整审核工作台截图
9. **最终交付包 `李_A_day08`** — `package_release --check` 所有闸门未通过，拒绝出包

## 契约疑点（记录，不做阻塞）

| # | 描述 | 须确认对象 |
|---|------|-----------|
| Q1 | `requirements.txt` torch 依赖仅有 `linux` 和 `darwin` marker，无 `win32` — Windows 宿主机 Conda 本地开发需手动处理 | 组长 |
| Q2 | `docs/TEAM_ROSTER.md` 中四名成员学号均标注"待补充"，为交付必要条件 | 组长/各成员 |
| Q3 | `outputs/` 为 volume mount (`:rw`)，但 `models/` 挂载为只读 (`:ro`) — 合约正确，待模型文件放置后验证 | CV |
