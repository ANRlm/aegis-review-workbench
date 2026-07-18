# 截图索引

> 状态：⛔ 所有截图待补（前端 `feature/frontend-workbench` 尚未合并）

## 必截截图清单

| # | 截图内容 | 文件名 | 状态 |
|---|---------|--------|------|
| 1 | 工作台首页（三栏布局） | `screenshots/workbench_full.png` | ⛔ 待补 |
| 2 | 上传成功后任务卡 | `screenshots/upload_success.png` | ⛔ 待补 |
| 3 | 分析进行中（queued/running 状态） | `screenshots/analysis_in_progress.png` | ⛔ 待补 |
| 4 | 完成结果 — pass（通过） | `screenshots/result_pass.png` | ⛔ 待补 |
| 5 | 完成结果 — review（待复核） | `screenshots/result_review.png` | ⛔ 待补 |
| 6 | 完成结果 — reject（不通过） | `screenshots/result_reject.png` | ⛔ 待补 |
| 7 | 证据帧展示 | `screenshots/evidence_frame.png` | ⛔ 待补 |
| 8 | 人工改判面板 | `screenshots/manual_review.png` | ⛔ 待补 |
| 9 | 历史任务列表 | `screenshots/history.png` | ⛔ 待补 |
| 10 | 统计面板 | `screenshots/stats.png` | ⛔ 待补 |
| 11 | JSON 下载内容 | `screenshots/download_json.png` | ⛔ 待补 |
| 12 | CSV 下载内容 | `screenshots/download_csv.png` | ⛔ 待补 |
| 13 | 审核包 ZIP 内容 | `screenshots/download_zip.png` | ⛔ 待补 |
| 14 | 错误提示（格式不支持） | `screenshots/error_unsupported.png` | ⛔ 待补 |
| 15 | 健康检查 / Docker 终端 | `screenshots/docker_health.png` | ⛔ 待补 |

## 纯文本证据（已保存）

| 文件 | 说明 |
|------|------|
| `tests/fixtures/media/homepage.html` | `docker compose up` 后首页 HTML（2026-07-18） |
| `tests/fixtures/media/health.json` | `docker compose exec app curl /api/health` 输出（2026-07-18） |

## 截图采集条件

前端 `feature/frontend-workbench` 合入后，使用浏览器（1366×768）逐一截取。
每张截图文件名与上表一致，保存至 `screenshots/`。

最终验收时本索引更新为 `✅ 已截` 并附截图文件链接。
