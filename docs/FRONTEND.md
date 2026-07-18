# 影鉴 Aegis Review 前端实现文档

## 概述

- 前端工程师：孙畅 (Helen-444)
- 分支：`feature/frontend-workbench-clean`
- 技术栈：原生 HTML、CSS、JavaScript（无框架）

## 页面结构（1366×768 桌面首屏）

```
+----------------------------------+-----------------------------------------+
| 品牌标识                          | 健康状态  ·  统计栏（总/通过/复核/拒绝/失败）|
+-------------+--------------------+-----------------------------------------+
| 新建任务     | 素材与证据           | 当前规则（风险类别/阈值）                |
| 项目名       | 空状态/加载/失败     | 审核操作                                |
| 拖放上传     | 素材预览             | 自动结论 / 最终结论                     |
| 规则阈值     | 检测汇总             | 人工改判 (pass/review/reject)           |
| [创建/分析]  | 证据帧网格           | 负责人（必填）/ 备注                    |
+-------------+--------------------+ JSON / CSV / ZIP 下载                   |
| 任务历史     |                    |                                         |
| 状态筛选     |                    |                                         |
+-------------+--------------------+-----------------------------------------+
```

布局：三栏网格 `300px minmax(0, 1fr) 300px`，上传入口集成在左栏顶部。

## 设计令牌

| 属性 | 值 |
|------|-----|
| 画布背景 | `#F7F7F3` |
| 表面颜色 | `#FFFFFF` |
| 正文颜色 | `#1E2422` |
| 辅助文字 | `#68716D` |
| 主色（青绿） | `#39766A` |
| 警告色（橙） | `#C26E1A` |
| 危险色（红） | `#C0392B` |
| 主圆角 | 17px |
| 动画时长 | 180ms |

## 四种页面状态

1. **空状态** - 首次进入，显示上传引导和空图示。
2. **加载中** - 选中任务后显示旋转指示器。
3. **失败态** - 展示后端 `error.message`，提供"重新分析"按钮。
4. **完成态** - 显示原素材、检测汇总、证据帧网格和审核面板。

## 状态转换流程

```
空 → 上传 → created → POST /analyze → queued → 轮询 → running → completed/failed
                                                                   ↓
                                                             展示报告/错误
```

## API 对接

固定消费 11 个端点，全部检查 `ok === true`，失败优先展示 `error.message`：

- `GET /api/health` — 服务、模型、FFmpeg 状态
- `GET /api/stats` — 审核统计
- `POST /api/jobs` — 创建任务（multipart/form-data）
- `POST /api/jobs/<id>/analyze` — 启动分析
- `GET /api/jobs` — 任务列表（支持 `?status=` 筛选）
- `GET /api/jobs/<id>` — 任务详情
- `DELETE /api/jobs/<id>` — 删除任务
- `PATCH /api/jobs/<id>/review` — 人工改判
- `GET /api/jobs/<id>/report` — 获取分析报告
- `GET /api/jobs/<id>/artifacts/<filename>` — 产物下载

## 下载安全

- CSV/ZIP 直接使用 `report.downloads` 中的完整 API URL
- 下载前验证 URL：同源检测 + pathname 前缀校验
- 非法 URL 显示中文错误，不发起导航
- JSON 报告序列化为 Blob 下载

## 轮询机制

- 使用递归 `setTimeout`（非 `setInterval`），上次请求完成后才排定下次
- `AbortController` 传入 fetch signal
- 切换任务、终态到达、网络错误时 `clearTimeout` + `abort`
- `fetchJob`/`fetchReport` 只返回数据，不直接写全局 state
- 调用者通过 `selectedJobId` token 确认后才写入

## model_ready 处理

- 按钮动态文案：模型就绪显示"创建并分析"，未就绪显示"仅创建任务"
- health 未加载或 model_ready=false 时禁止发送 analyze 请求
- created/failed 任务的"开始分析/重新分析"按钮同步禁用
- `updateUploadButton()` 同时检查项目名和文件状态
- 创建任务后若模型未就绪，仅创建记录不触发分析

## 数值解析

- 使用 `parseNumeric(value, default)` 函数
- 空字符串使用默认值，`Number.isFinite()` 校验
- 合法 0 保留，不用 `|| default` 短路

## 响应式设计

| 视口 | 布局 |
|------|------|
| >=1060px | 三栏 300px + 1fr + 300px |
| 860-1060px | 窄三栏 260px + 1fr + 260px |
| 500-860px | 单列 |
| <500px | 单列紧凑 |

窄屏无横向滚动，`document.documentElement.scrollWidth === document.documentElement.clientWidth`。

## 可访问性

- 语义 HTML（main, header, nav, aside, section, fieldset）
- aria-label 标注所有交互区域
- role="status" / aria-live="polite" 用于动态内容
- 显式 `:focus-visible` 焦点环
- `<dialog>` + `aria-modal="true"` 确认框
- 删除按钮带 `aria-label="删除任务 <名称>"`
- 键盘 Enter/Space 在删除按钮上打开确认框，不切换任务
- `prefers-reduced-motion` 禁用所有动画

## 状态徽章

- 使用 CSS class（`.status-running`, `.status-created`）替代 inline style
- 切换状态时 `removeAttribute("style")` 清除旧行内样式

## 截图清单

| 文件 | 视口 | 状态 |
|------|------|------|
| `screenshots/empty_1366x768.png` | 1366×768 | 空状态 / model_ready=false |
| `screenshots/running_1366x768.png` | 1366×768 | running |
| `screenshots/failed_1366x768.png` | 1366×768 | failed |
| `screenshots/completed_1366x768.png` | 1366×768 | completed |
| `screenshots/review_1366x768.png` | 1366×768 | 人工改判 |
| `screenshots/mobile_390x844.png` | 390×844 | 窄屏单列 |

> 截图待后端 API 全部就绪后从真实运行页面截取。
