# 最终截图索引

> 采集：2026-07-18
> 环境：Docker 正式服务 + 真实模型 + 应用内浏览器
> 原则：不注入 DOM，不伪造任务状态

桌面截图基于 1366×768 视口；`history.png` 与 `stats.png` 是从该视口直接截取
的真实局部区域。移动端使用浏览器真实 viewport override，页面内
`window.innerWidth=390`、`window.innerHeight=844`。

| # | 文件名 | 视口/区域 | 真实操作与结果 | Job ID |
|---:|---|---|---|---|
| 1 | `workbench_full.png` | 1366×768 | 三栏工作台、健康徽标和历史 | 多任务 |
| 2 | `upload_success.png` | 1366×768 | 浏览器上传 `sample_5s.mp4` 成功 | `20260718_123440_32cabc08` |
| 3 | `analysis_in_progress.png` | 1366×768 | 视频真实 running 与创建成功提示 | `20260718_123440_32cabc08` |
| 4 | `result_pass.png` | 1366×768 | 风险类设为不存在类别，结论通过 | `20260718_122823_c8db0377` |
| 5 | `result_review.png` | 1366×768 | enemy 风险进入待复核档 | `20260718_122853_5f664a01` |
| 6 | `result_reject.png` | 1366×768 | 默认规则命中高置信 enemy | `20260718_122853_c15ec8f0` |
| 7 | `evidence_frame.png` | 1366×768 | 标注帧、enemy 99.8% 和汇总 | `20260718_122853_c15ec8f0` |
| 8 | `manual_review.png` | 1366×768 | 自动拒绝人工改为待复核，负责人李佳铭 | `20260718_122854_4fc3df62` |
| 9 | `history.png` | 任务列表区域 | 历史任务重开与终态列表 | 多任务 |
| 10 | `stats.png` | 顶部统计区域 | 总数及 pass/review/reject/failed | 多任务 |
| 11 | `download_json.png` | 1366×768 | 点击 JSON 报告 | `20260718_122854_4fc3df62` |
| 12 | `download_csv.png` | 1366×768 | 点击 CSV 检测表 | `20260718_122854_4fc3df62` |
| 13 | `download_zip.png` | 1366×768 | 点击 ZIP 审核包 | `20260718_122854_4fc3df62` |
| 14 | `error_unsupported.png` | 1366×768 | 上传 `.bmp`，页面显示真实后端错误 | — |
| 15 | `docker_health.png` | 1366×768 | Docker 页面服务/模型/FFmpeg 三项就绪 | 多任务 |
| 16 | `mobile_390x844.png` | 390×844 | 单列紧凑布局、无横向溢出 | 多任务 |

三种下载另通过 HTTP 直接复核：JSON 可解析、CSV 为 64 行、ZIP
`testzip() is None`。健康接口原始响应记录在 `docs/TEST_REPORT.md`。
