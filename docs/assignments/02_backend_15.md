# 02 后端工程师任务书（15%）

## 目标

严格按照 `docs/API.md` 实现 Flask 接口、上传校验、统一错误响应和安全产物下载。后端只负责编排 HTTP 输入输出，不复制 CV 规则或直接操作 Ultralytics。

## 前置阅读

1. `docs/API.md`
2. `docs/SYSTEM_DESIGN.md`
3. `aegis_review/domain.py`
4. `aegis_review/service.py`
5. `tests/test_contract.py`

从最新 `main` 创建 `feature/backend-api`，确认个人 Git 身份后再提交。

## 独占路径

- `aegis_review/api.py`
- `aegis_review/errors.py`
- `aegis_review/validation.py`
- `tests/test_api.py`
- `tests/test_validation.py`
- `docs/API.md`

不得修改 `aegis_review/cv/`、`templates/` 或 `static/`。

## 固定依赖接口

后端调用组长的服务对象，不绕过服务直接写任务 JSON：

```python
service.create_job(asset, project_name, settings) -> dict
service.enqueue_analysis(job_id) -> dict
service.list_jobs(status=None) -> list[dict]
service.get_job(job_id) -> dict
service.delete_job(job_id) -> None
service.review_job(job_id, decision, reviewer, note) -> dict
service.get_report(job_id) -> dict
service.resolve_artifact(job_id, filename) -> pathlib.Path
service.stats() -> dict
```

若实际 `service.py` 缺少或更改上述签名，停止开发并通知组长先更新契约。

## 工作包

### B1：请求验证

- `project_name` 去除空格后 1–80 字；
- 只接受单个 `asset`；
- 扩展名仅 `jpg/jpeg/png/mp4/mov`；
- 检查空流和 200MB 上限；
- 图片使用 OpenCV/Pillow 实际解码；
- 视频使用 OpenCV 打开并至少读取一帧；
- `settings` 解析为 JSON 对象并构造 `AuditSettings`；
- 校验失败不创建任务目录。

### B2：任务接口

- 实现创建、入队、列表、详情、删除；
- 严格使用 201/202/200/400/404/409/413；
- 列表支持可选 `status`；
- 入队后立即返回，不等待 pipeline；
- 运行中删除返回 `job_busy`。

### B3：审核与产物

- 改判仅允许完成任务；
- `decision` 只允许 `pass/review/reject`；
- `reviewer` 1–40 字且非空；
- `note` 最多 500 字；
- 报告响应保留自动结论；
- 产物只允许报告白名单中的 basename；
- 文件响应使用安全下载名，不暴露绝对路径。

### B4：统一异常

- 已知领域异常映射为固定错误码；
- API 404 使用结构化 JSON；
- 未知 API 异常返回 `internal_error` 并记录服务日志；
- 响应中不出现堆栈、本机路径或模型内部对象；
- 参数错误不能终止 Flask 进程。

## 必测场景

- 健康检查；
- 合法图片创建返回 201；
- 分析返回 202；
- 缺文件、空文件、错误扩展名、损坏媒体；
- 无效规则阈值；
- 任务不存在；
- 重复分析；
- 运行中删除；
- 合法与非法人工改判；
- 合法产物和 `../` 越界产物。

测试使用 Flask test client 和临时目录，不加载真实 YOLO。

## 建议提交

1. `test: define upload and validation API cases`
2. `feat: implement job and analysis routes`
3. `feat: add review report and safe artifact routes`
4. `docs: finalize API examples and error codes`

每次提交前运行：

```bash
pytest -q tests/test_contract.py tests/test_validation.py tests/test_api.py
git diff --check
```

## 验收标准

- `docs/API.md` 的全部接口均有测试；
- 成功响应都有 `ok: true`；
- 失败响应都有结构化 `error`；
- 至少两个 API 测试不是 mock 路由；
- 不支持格式、空文件和解码失败不会创建残留任务；
- 路径穿越测试返回 404。

## 停止条件

发现服务签名、状态枚举、报告字段或目录结构与契约不一致时，不自行发明兼容层；记录冲突并让组长先决定。
