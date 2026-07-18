# 真实 Bug 记录

> 初始记录：朱可心（xin-rabbit）
> 最终联调与复验：李佳铭（ANRlm）
> 更新：2026-07-18
> 状态：4 个真实 Bug 已闭环

所有条目均来自真实实现或联调，不使用预先编造的故障。处理流程为：失败现象
→ 最小回归测试 → 根因定位 → 独立修复提交 → 新鲜回归。

## BUG-001 `[hidden]` 元素被布局样式覆盖

- 现象：部分应隐藏的加载、失败或内容容器仍参与布局，页面状态可能同时显示。
- 环境：前端工作台，桌面与窄屏均可复现。
- 复现：切换任务状态，检查带有 `hidden` 属性的状态容器；基础样式没有稳定覆盖后续布局规则。
- 根因：`[hidden] { display: none !important; }` 被误放在
  `prefers-reduced-motion` 媒体查询内，未启用减少动画的用户不会获得该规则。
- 证据：`tests/test_frontend_contract.py::test_css_hidden_rule_in_base_reset_not_inside_media_query`。
- 修复：将 `[hidden]` 规则移到基础 reset 区，并增加位置回归断言。
- 责任模块：前端。
- 修复提交：8efc7ea
- 回归命令：`pytest -q tests/test_frontend_contract.py`
- 回归结果：通过

## BUG-002 模型显示就绪但分析器仍不可用

- 现象：`GET /api/health` 返回 `model_ready=true`，上传后的任务却失败并提示
  “CV 分析组件尚未就绪”。
- 环境：模型权重已挂载的 Docker 正式服务。
- 复现：启动含 `models/aegis_game_best.pt` 的服务，确认健康检查后创建并分析图片。
- 根因：健康检查只验证权重文件存在，而默认应用工厂仍固定注入
  `UnavailableAnalyzer`，没有把训练权重绑定到真实 `analyze_asset`。
- 证据：PR #8 的集成回归，以及最终真实图片任务
  `20260718_122853_c15ec8f0` 成功完成并生成证据、CSV 与 ZIP。
- 修复：应用工厂在权重存在时调用 `bind_analyzer(model_path=...)`，权重缺失时才使用不可用分析器。
- 责任模块：组长集成。
- 修复提交：1ffeb74
- 回归命令：`pytest -q tests/test_app_factory.py tests/test_acceptance.py`
- 回归结果：通过

## BUG-003 Windows 无法打开目录文件描述符

- 现象：Windows 本机执行原子存储测试时在
  `os.open(directory, os.O_RDONLY)` 抛出 `PermissionError`，导致服务测试连带失败。
- 环境：Windows + Python 3.11；Docker/Linux 与 macOS 不复现。
- 复现：在 Windows 执行
  `pytest -q tests/test_storage.py tests/test_app_factory.py`。
- 根因：文件级 `flush + fsync` 可用，但 Windows 不支持以 Unix 方式打开目录 FD
  再进行目录 `fsync`。
- 证据：新增测试模拟 `os.name == "nt"`，断言不会调用 `os.open(directory)`，
  同时 JSON 仍经 `flush + fsync + os.replace` 成功写入。
- 修复：增加 `_directory_fsync_supported()`；Windows 跳过目录 FD fsync，
  Unix/macOS 保持原行为。
- 责任模块：组长存储。
- 修复提交：25c799c
- 回归命令：`pytest -q tests/test_storage.py tests/test_app_factory.py`
- 回归结果：通过

## BUG-004 发布校验查错 ZIP 证据路径

- 现象：生产管线的审核包包含 `evidence/frame_*.jpg`，发布校验却在 ZIP
  根目录查找 `frame_*.jpg`，导致合法 completed job 被误判为损坏。
- 环境：`scripts/package_release.py --check`，真实图片与视频产物。
- 复现：构造只在 `evidence/frame_001.jpg` 存放证据的合法审核包并调用
  `_validate_completed_job()`。
- 根因：校验器直接使用报告中的 basename，没有补上生产 ZIP 的
  `evidence/` 成员前缀。
- 证据：D10 回归夹具改为生产目录结构；新增“只有根目录证据必须拒绝”的反例。
- 修复：逐个检查 `evidence/{evidence_file}`，错误信息返回完整 ZIP 成员名。
- 责任模块：测试与交付。
- 修复提交：6b0342e
- 回归命令：`pytest -q tests/test_delivery.py`
- 回归结果：通过
