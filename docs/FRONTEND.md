# 影鉴 Aegis Review 前端实现文档

## 概述

- 前端工程师：孙畅 (Helen-444)
- 分支：`feature/frontend-workbench`
- 技术栈：原生 HTML、CSS、JavaScript（无框架）

## 页面结构

```
+--------------------------------------------------+
| 品牌标识 · 健康状态 (服务 / 模型 / FFmpeg)        |
+--------------------------------------------------+
| 统计栏 (总任务 / 通过 / 待复核 / 不通过 / 失败)   |
+--------------------------------------------------+
| 新建任务 (项目名 / 拖放上传 / 规则阈值设置)       |
+------------+---------------------+---------------+
| 任务历史    | 素材与证据           | 审核操作      |
| 状态筛选    | 空状态/加载/失败     | 自动/最终结论 |
| 任务列表    | 素材预览             | 人工改判      |
| 删除确认    | 检测汇总             | 负责人/备注   |
|            | 证据帧网格           | JSON/CSV/ZIP  |
+------------+---------------------+---------------+
```

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

## 响应式设计

| 视口 | 布局 |
|------|------|
| >=1060px | 三栏 280px + 1fr + 280px |
| 860-1060px | 窄三栏 240px + 1fr + 240px |
| 500-860px | 单列，任务历史限高 240px |
| <500px | 单列紧凑，统计弹性伸缩 |

窄屏无横向滚动，核心操作可见。

## 可访问性

- 语义 HTML（main, header, nav, aside, section, fieldset）
- aria-label 标注所有交互区域
- role="status" / aria-live="polite" 用于动态内容
- 显式 `:focus-visible` 焦点环
- `<dialog>` + `aria-modal="true"` 确认框
- `prefers-reduced-motion` 禁用所有动画

## 轮询管理

- 每任务 1 秒独立轮询
- 切换任务、终态到达、页面卸载时 `clearInterval`
- fetch 回调中比对 `selectedJobId` 避免过期请求

## 截图清单

| 文件 | 视口 | 状态 |
|------|------|------|
| `screenshots/empty_1366x768.png` | 1366×768 | 空状态 |
| `screenshots/running_1366x768.png` | 1366×768 | running |
| `screenshots/failed_1366x768.png` | 1366×768 | failed |
| `screenshots/completed_1366x768.png` | 1366×768 | completed |
| `screenshots/review_1366x768.png` | 1366×768 | 人工改判 |
| `screenshots/mobile_390x844.png` | 390×844 | 窄屏单列 |

> 截图待后端 API 全部就绪后从真实运行页面截取。
