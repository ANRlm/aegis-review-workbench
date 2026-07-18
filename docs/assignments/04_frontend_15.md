# 04 前端工程师任务书（15%）

## 目标

把当前契约说明页替换为完整桌面审核工作台。前端必须消费真实 API 状态和报告，不允许写死任务、统计、检测框或审核结论。

## 前置阅读

1. `docs/PRD.md`
2. `docs/API.md`
3. `docs/SYSTEM_DESIGN.md`
4. 当前 `templates/index.html`
5. 当前 `static/styles.css`

从最新 `main` 创建 `feature/frontend-workbench`。

## 独占路径

- `templates/`
- `static/`
- `screenshots/`
- `tests/test_frontend_contract.py`
- `docs/FRONTEND.md`

不得修改 Flask API、CV 和任务服务。

## 视觉系统

- 暖白画布 `#F7F7F3`；
- 白色表面、石墨正文、低饱和青绿主色；
- 待复核使用克制橙色，不通过使用克制红色；
- 主圆角 16–18px，轻边框，避免大面积阴影、霓虹和渐变；
- 字体使用系统中文无衬线；
- 动画 160–240ms；
- 支持 `prefers-reduced-motion`；
- 1366×768 首屏完成核心审核；窄屏变单列且无横向滚动。

## 页面结构

### 顶部

- 品牌与简短系统名；
- `/api/health` 的服务、模型、FFmpeg 状态；
- 总任务、通过、待复核、不通过统计。

### 左侧任务轨

- 上传入口与拖放反馈；
- 项目名和规则阈值表单；
- 历史任务列表；
- 状态、素材名、创建时间；
- 状态筛选和删除操作。

### 中部证据区

- 图片或视频原素材预览；
- 空状态、加载状态、失败状态；
- 完成态显示自动结论和检测汇总；
- 证据帧网格，显示时间、类别、置信度；
- 不构造浏览器本地假检测框。

### 右侧审核区

- 当前自动结论和最终结论；
- `pass/review/reject` 三项人工选择；
- 必填负责人、可选备注；
- 保存改判；
- JSON、CSV、ZIP 下载。

## 交互流程

1. 校验项目名、文件和阈值；
2. `POST /api/jobs`；
3. 成功后自动 `POST /analyze`；
4. 每 1 秒查询任务详情；
5. 到达 `completed/failed` 停止轮询；
6. 完成后请求报告和统计；
7. 切换历史任务可重新打开；
8. 改判成功后立即刷新报告和统计；
9. 删除后清空选中项并刷新列表。

页面卸载、切换任务或进入终态时必须取消旧定时器，避免重复轮询。

## 状态与错误

- 首次进入：清晰的上传引导；
- `created/queued/running`：显示真实状态文字，不伪造百分比；
- `failed`：显示后端 error；
- `completed`：显示报告；
- 400/404/409/413：显示后端中文 message；
- 网络失败：提示可以重试，不把任务误标为失败；
- 模型未 ready：禁用分析并保留健康说明。

## 建议提交

1. `feat: build responsive Aegis Review workspace`
2. `feat: connect upload polling and history workflow`
3. `feat: add evidence review and export interactions`
4. `test: verify frontend states responsive layout and motion`

## 验证

```bash
node --check static/app.js
pytest -q tests/test_frontend_contract.py
```

浏览器手工验证：

- 1366×768；
- 1440×900；
- 390×844；
- 键盘 Tab 顺序和可见焦点；
- 空、queued/running、failed、completed；
- `prefers-reduced-motion`；
- 长文件名、长错误和 120 个证据项。

将真实页面截图保存到 `screenshots/`，在 `docs/FRONTEND.md` 说明视口和交互。

## 验收标准

- 全部操作使用真实 API；
- 轮询不会重入或泄漏；
- 四种页面状态完整；
- 人工改判要求负责人；
- 三种报告下载可用；
- 1366×768 首屏无内部意外滚动；
- 390px 无横向溢出；
- 动画关闭偏好有效。

## 停止条件

API 字段、状态或错误结构与 `docs/API.md` 不一致时停止，向组长和后端成员报告。不得在前端添加临时兼容字段掩盖契约冲突。
