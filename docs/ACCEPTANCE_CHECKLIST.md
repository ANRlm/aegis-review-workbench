# 验收清单

| # | 验收条件 | 证据指针 | 状态 |
|---|---------|---------|------|
| 1 | README 从干净容器可启动 | `docker compose up -d` + `curl /api/health` 通过 | ✅ Docker 构建+启动通过 |
| 2 | `/api/health` 正常并说明依赖状态 | `{"ok":true,"model_ready":false,"ffmpeg_ready":true,"storage_ready":true}` | ✅ 真实反映依赖 |
| 3 | 上传后先返回任务 ID | — | ⛔ 后端未合并 |
| 4 | 状态真实变化（created→queued→running→completed） | — | ⛔ 后端未合并 |
| 5 | 至少一次真实自训练模型推理 | — | ⛔ CV+模型未合并 |
| 6 | 图片三档结论（pass/review/reject） | — | ⛔ CV 注入 seam 未暴露 |
| 7 | 视频异步处理与证据帧 | — | ⛔ CV+模型未合并 |
| 8 | 人工改判写回报告且保留 auto_decision | — | ⛔ 后端未合并 |
| 9 | 历史任务重开（刷新后仍在） | — | ⛔ 后端未合并 |
| 10 | JSON/CSV/ZIP 下载可读可校验 | validator 自检通过 | ✅ 校验器就绪（待真实产物） |
| 11 | 统计随最终结论更新 | — | ⛔ 后端未合并 |
| 12 | 失败任务保留 `job.json` | — | ⛔ 后端未合并 |
| 13 | 不支持格式 / 空文件 / 损坏媒体提示 | domain 层校验通过 | ✅ domain 就绪（待 API 层） |
| 14 | 5 条正常测试 + 5 条异常测试 | `TEST_REPORT.md` 矩阵 | ✅ 矩阵完整（27 skip=阻塞依赖） |
| 15 | 2 个真实 Bug（失败证据+修复+复验） | `BUG_RECORD.md` | ⛔ 0 个（联调未开始） |
| 16 | Docker、Conda、健康检查有记录 | `TEST_REPORT.md` | ✅ Docker 验证完整 |
| 17 | 页面截图和结果截图完整 | `SCREENSHOT_INDEX.md` | ⛔ 0 张（前端未合并） |
| 18 | 五名成员可通过 Git 核验贡献 | `CONTRIBUTIONS.md` | ✅ 基于真实 shortlog（待其他成员提交） |
| 19 | 8 分钟演示稿可现场复现 | — | ⛔ 功能未齐全 |
| 20 | 最终包 `李_A_day08`（无隐私/缓存/大文件） | `package_release.py --check` | ⛔ 8/8 闸门未过 |
| 21 | 无密钥、无隐私绝对路径 | hygiene_scan（容器无 git → 宿主机补跑） | ⚠️ 容器跳过 |
| 22 | 提交记录完整、作者映射正确 | `git shortlog -sne --all` | ✅ 骨架 = 组长 3 提交 |

## 通过 / 阻塞统计

| 状态 | 数量 |
|------|------|
| ✅ 通过 | 6 |
| ⛔ 阻塞（依赖未合并） | 14 |
| ⚠️ 待验证 | 2 |
| **总计** | **22** |
