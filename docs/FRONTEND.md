# 影鉴 Aegis Review 前端工作台

## 实现概要

将契约说明页替换为三栏审核工作台，消费后端真实 API。

### 页面布局

| 区域 | 内容 |
|---|---|
| 顶部栏 | 品牌标识、健康状态（模型/FFmpeg/存储）、任务统计 |
| 左侧面板（320px） | 上传表单（项目名、文件选择、拖放区、规则阈值）、历史任务列表、状态筛选 |
| 中部面板（1fr） | 空状态引导、加载状态、失败状态、完成态（素材预览、检测汇总、证据帧） |
| 右侧面板（300px） | 自动/最终结论、人工改判三选、负责人、备注、保存、下载 |

### 视觉系统

- 暖白画布 `#F7F7F3`，白色表面，石墨色正文
- 低饱和青绿主色（`#39766A`）
- 橙色仅用于 `review`（`#C9743A`），红色仅用于 `reject`（`#B53B3B`）
- 主圆角 16px，轻边框，无大面积阴影
- 动画 200ms ease，支持 `prefers-reduced-motion`

### 四种页面状态

| 状态 | 显示内容 |
|---|---|
| 空状态 | 上传引导文字和支持格式说明 |
| 加载中 | 旋转动画 + 状态文字（排队中…/分析中…） |
| 失败 | 红色感叹号 + 后端返回的错误 message |
| 完成 | 素材预览、自动结论、检测表格、证据帧网格 |

## API 对接

前端仅调用以下端点：

| 端点 | 用途 | 频率 |
|---|---|---|
| `GET /api/health` | 页面初始化 | 首次加载 |
| `GET /api/stats` | 统计数字 | 初始化 + 每次终态后 |
| `POST /api/jobs` | 创建任务 | 上传提交 |
| `POST /api/jobs/<id>/analyze` | 启动分析 | 创建成功后 |
| `GET /api/jobs` | 历史列表 | 初始化 + 每次变更后 |
| `GET /api/jobs/<id>` | 任务详情与轮询 | 每秒（非终态） |
| `GET /api/jobs/<id>/report` | 分析报告 | 完成态时 |
| `PATCH /api/jobs/<id>/review` | 人工改判 | 点击保存 |
| `DELETE /api/jobs/<id>` | 删除任务 | 确认删除 |
| `GET /api/jobs/<id>/artifacts/<file>` | 证据帧与下载 | 完成态展示 |

## 交互流程

1. 页面加载 → `GET /health` + `GET /stats` + `GET /jobs`
2. 用户填写项目名、选择/拖放文件、可选调整阈值
3. 提交 → `POST /jobs` → `POST /analyze` → 选中新任务
4. 每秒 `GET /jobs/<id>` 轮询，切换任务/到达终态/页面卸载时停止
5. 到达 `completed` → `GET /jobs/<id>/report` + 更新统计
6. 到达 `failed` → 显示后端错误
7. 人工改判 → 选择结论 + 必填负责人 + 可选备注 → `PATCH /review`
8. 下载 → JSON（报告端点）、CSV、ZIP（产物白名单）

## 测试结果

```bash
node --check static/app.js
pytest -q tests/test_frontend_contract.py
```

## 截图

| 截图文件 | 视口 | 状态 | 说明 |
|---|---|---|---|
| `screenshots/empty.png` | 1366×768 | 空状态 | 首次加载页面 |
| `screenshots/running.png` | 1366×768 | 运行中 | 任务分析过程中 |
| `screenshots/completed.png` | 1366×768 | 已完成 | 检测结果与证据展示 |
| `screenshots/failed.png` | 1366×768 | 失败 | 后端错误显示 |
| `screenshots/narrow.png` | 390×844 | 任务完成 | 窄屏单列布局 |

## 提交记录

| 提交 | 说明 |
|---|---|
| `feat: build responsive Aegis Review workspace` | HTML 骨架、CSS token、焦点样式、三栏布局 |
| `feat: connect upload polling and history workflow` | 上传、轮询、历史、状态管理 |
| `feat: add evidence review and export interactions` | 证据展示、人工改判、三种下载 |
| `test: verify frontend states responsive layout and motion` | 契约测试 |

## 验收项

- [x] 全部操作使用真实 API
- [x] 轮询无重入或泄漏（切换/终态/卸载时 `clearInterval`）
- [x] 四种页面状态完整
- [x] 人工改判要求负责人
- [x] JSON/CSV/ZIP 下载可用
- [x] 1366×768 首屏布局稳定
- [x] 390px 无横向溢出
- [x] 键盘焦点可见（`focus-visible`）
- [x] `prefers-reduced-motion` 生效
- [x] 未修改后端、CV 和组长独占模块

## 遗留问题

- 后端 API 路由尚未实现时部分功能不可用
- CV 分析组件未就绪时分析会返回 failed
