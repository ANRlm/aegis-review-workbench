# 影鉴 Aegis Review 前端实现文档

## 概述

- 前端工程师：孙畅（Helen-444）
- 最终 PR：#6 `feature/frontend-workbench-clean`
- 技术栈：原生 HTML、CSS、JavaScript
- 最终状态：已合入并通过真实 Docker 端到端验收

## 页面结构

桌面使用 `300px minmax(0, 1fr) 300px` 三栏：左侧上传与历史，中部素材、
检测汇总和证据，右侧规则、人工审核和下载。顶部持续显示服务、模型、
FFmpeg 与三档统计。

页面完整覆盖空状态、加载/分析中、失败态和完成态：

```text
空 → 上传 → created → queued → running → completed/failed
                                      └→ 报告/证据/改判/导出
```

## 设计系统

| 属性 | 值 |
|---|---|
| 画布 | `#F7F7F3` 暖白 |
| 正文 | `#1E2422` 石墨 |
| 主色 | `#39766A` 低饱和青绿 |
| 警告 | `#C26E1A` |
| 危险 | `#C0392B` |
| 主圆角 | 17px |
| 动画 | 180ms |

所有动画在 160–240ms 的克制范围，并由 `prefers-reduced-motion` 完整关闭。
`[hidden] { display: none !important; }` 位于基础 reset，避免状态容器被布局规则
重新显示（BUG-001）。

## API 与轮询

- 所有响应检查 `ok === true`，失败优先显示 `error.message`。
- 上传使用 multipart；创建成功后自动发起分析。
- 使用递归 `setTimeout` 每秒轮询，切换任务、终态、卸载和网络错误都会清理
  timer 与 `AbortController`。
- 不伪造百分比；瞬时 running 只显示真实状态。
- `model_ready=false` 时不发送分析请求。
- 人工改判要求非空负责人，保留自动结论。
- JSON 使用 Blob 下载；CSV/ZIP 使用经过同源与路径前缀校验的产物 URL。

## 响应式与可访问性

| 视口 | 布局 |
|---|---|
| ≥1060px | 300px + 1fr + 300px |
| 860–1059px | 260px + 1fr + 260px |
| 500–859px | 单列 |
| <500px | 单列紧凑 |

最终 390×844 真实截图显示单列布局，无横向溢出。页面使用语义
`main/header/nav/aside/section/fieldset`、ARIA live region、明确焦点环、
带标签的删除按钮和原生确认对话框。

## 最终截图

15 张发布门禁截图与一张移动端截图已存入 `screenshots/`。其中：

- `analysis_in_progress.png`：真实视频 running；
- `result_pass/review/reject.png`：真实模型三档结论；
- `manual_review.png`：负责人李佳铭的真实改判；
- `error_unsupported.png`：真实 `.bmp` 错误；
- `mobile_390x844.png`：真实 390×844 视口。

完整映射见 `docs/SCREENSHOT_INDEX.md`。
