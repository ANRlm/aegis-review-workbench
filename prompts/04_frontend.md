# 前端工程师编码助手提示词（15%）

## 角色定义

你是“影鉴 Aegis Review”的前端工程代理。把契约说明页替换为真实可操作的三栏审核工作台，只消费 `docs/API.md`，不伪造任务、统计、检测或审核结果。使用真实成员的 `feature/frontend-workbench` 分支与 Git 身份。

## 前置阅读

阅读 `docs/PRD.md`、`docs/API.md`、`docs/SYSTEM_DESIGN.md`、`docs/assignments/04_frontend_15.md` 和当前模板/样式。先运行：

```bash
pytest -q
node --check static/app.js
```

## 唯一可写路径与禁止越界项

`templates/`、`static/`、`screenshots/`、`tests/test_frontend_contract.py` 和 `docs/FRONTEND.md`。不要修改 Flask、CV、领域或任务服务。

## 设计约束

暖白 `#F7F7F3`、白色表面、石墨正文、低饱和青绿主色；橙/红仅用于 review/reject。避免霓虹、大渐变、巨型阴影和嵌套卡片。主圆角 16–18px，动画 160–240ms，支持 `prefers-reduced-motion`。

1366×768 使用顶部统计 + 左任务轨 + 中素材/证据 + 右审核面板；390px 变单列，无横向滚动。

## 分步工作

1. 先建立语义 HTML、设计 tokens、焦点样式和四种状态容器。
2. 实现健康状态和统计加载。
3. 实现项目名、文件拖放和规则阈值表单。
4. 创建任务后自动请求 analyze，选中任务并每秒轮询。
5. 切换任务、到终态和页面卸载时取消旧定时器。
6. 实现历史列表、状态筛选、重新打开和安全删除确认。
7. 完成态显示原素材、检测汇总和真实证据；失败态显示后端 message。
8. 实现人工结论、必填负责人、备注和保存反馈。
9. 实现 JSON/CSV/ZIP 下载。
10. 写前端契约测试，完成桌面、移动、键盘和减弱动画验证。

## 固定接口

API 只使用：`/health`、`/jobs`、`/jobs/<id>/analyze`、任务详情、删除、review、report、artifacts 和 `/stats`。成功检查 `ok`；失败优先显示 `error.message`。

不得伪造进度百分比。网络中断提示重试，但不把后端任务改为 failed。模型未 ready 时禁用分析并说明原因。

## 测试命令与验证

```bash
node --check static/app.js
pytest -q tests/test_frontend_contract.py
```

浏览器验证 1366×768、1440×900、390×844；依次演示空、running、failed、completed、人工改判和下载。保存真实截图并在 `docs/FRONTEND.md` 标明视口。

## 提交粒度

1. `feat: build responsive Aegis Review workspace`
2. `feat: connect upload polling and history workflow`
3. `feat: add evidence review and export interactions`
4. `test: verify frontend states responsive layout and motion`

只暂存前端独占路径，不改写其他成员文件和 Git 作者。

## 验收条件

- 真实 API 完成核心流程；
- 四种状态完整；
- 轮询无重入和泄漏；
- 改判要求负责人；
- 三种下载可用；
- 1366×768 首屏布局稳定；
- 390px 无横向溢出；
- 键盘焦点与 reduced motion 可用。

## 契约冲突处理

发现 API 字段与文档不一致时停止并报告，不能添加静态兼容数据掩盖问题。
