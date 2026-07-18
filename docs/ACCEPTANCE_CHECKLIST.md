# 最终验收清单（2026-07-18）

| # | 条件 | 状态 | 证据 |
|---:|---|---|---|
| 1 | Docker 构建与启动 | ✅ | build、compose、health 新鲜通过 |
| 2 | `/api/health` 真实依赖 | ✅ | model/FFmpeg/storage 全 true |
| 3 | 上传返回 Job ID | ✅ | 浏览器任务 `20260718_123440_32cabc08` |
| 4 | created/queued/running/completed/failed | ✅ | 服务与 HTTP 状态机测试 |
| 5 | 真实模型推理 | ✅ | 五个正式 completed 任务 |
| 6 | pass/review/reject 三档 | ✅ | 三个真实图片 Job ID |
| 7 | 视频异步分析 | ✅ | `20260718_122855_9b72ccef` |
| 8 | 人工改判保留自动结论 | ✅ | `20260718_122854_4fc3df62` |
| 9 | 历史重开 | ✅ | 页面历史与详情重载测试 |
| 10 | JSON/CSV/ZIP | ✅ | HTTP 下载、解析、CRC |
| 11 | 最终结论统计 | ✅ | 顶部统计与 API 测试 |
| 12 | 失败任务保留 `job.json` | ✅ | analyzer failure 与恢复测试 |
| 13 | 格式/空文件/损坏/超限 | ✅ | API 与 acceptance 异常矩阵 |
| 14 | 5+ 正常、5+ 异常矩阵 | ✅ | N1–N8、A1–A12 |
| 15 | 至少 2 个真实 Bug | ✅ | 4 个闭环 Bug |
| 16 | Docker/health 记录 | ✅ | 测试报告与截图 |
| 17 | 15 张门禁截图 | ✅ | 15 张 + 1 张移动端 |
| 18 | 五人贡献核验 | ✅ | shortlog 与 PR #4/#5/#6/#8 |
| 19 | 8 分钟演示稿 | ✅ | `docs/DEMO_SCRIPT.md` |
| 20 | 最终包 `李_A_day08.zip` | ✅ | 八项门禁、双构建一致性与 CRC 通过 |
| 21 | 无密钥/隐私路径 | ✅ | 宿主机 hygiene 全通过 |
| 22 | 提交作者映射 | ✅ | 姓名、学号、GitHub、邮箱完整 |

最终：✅ 22 / ⏳ 0 / ⛔ 0。
