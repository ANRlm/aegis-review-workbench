# 影鉴 Aegis Review API 契约

基础地址：`http://127.0.0.1:7880/api`

## 1. 通用响应

成功响应包含 `ok: true`。错误响应固定为：

```json
{
  "ok": false,
  "error": {
    "code": "invalid_asset",
    "message": "上传文件无法解码。"
  }
}
```

常用错误码：`invalid_request`、`invalid_asset`、`invalid_settings`、`job_not_found`、`invalid_status`、`model_unavailable`、`artifact_not_found`、`job_busy`、`internal_error`。

## 2. 数据类型

### Job

```json
{
  "job_id": "20260718_101530_a1b2c3d4",
  "project_name": "星港遗迹内容审核",
  "asset_name": "opening_scene.mp4",
  "asset_type": "video",
  "asset_url": "/api/jobs/20260718_101530_a1b2c3d4/artifacts/original.mp4",
  "status": "completed",
  "created_at": "2026-07-18T10:15:30+08:00",
  "started_at": "2026-07-18T10:15:31+08:00",
  "completed_at": "2026-07-18T10:16:08+08:00",
  "settings": {},
  "result_file": "analysis_report.json",
  "error": null
}
```

`status` 只允许 `created | queued | running | completed | failed`。

`asset_url` 由后端根据任务中持久化的安全文件名生成。磁盘记录只保存
`asset_file`（例如 `original.mp4`），不保存 HTTP 地址，也不使用用户原文件名
作为磁盘路径。

### Detection

```json
{
  "frame_index": 30,
  "timestamp_seconds": 2.0,
  "class_id": 1,
  "class_name": "enemy",
  "confidence": 0.73,
  "bbox_xyxy": [108.2, 93.7, 236.5, 402.1],
  "evidence_file": "frame_000030.jpg"
}
```

磁盘中的 `analysis_report.json` 只保存下载产物 basename，例如
`detections.csv` 和 `audit_package.zip`。后端返回 HTTP 报告时再将其派生为
上述 `/api/jobs/<job_id>/artifacts/<filename>` URL；CV 管线不拼接 HTTP 地址。

### Report

```json
{
  "job_id": "20260718_101530_a1b2c3d4",
  "detections": [],
  "evidence_frames": ["frame_000030.jpg"],
  "rules": {},
  "auto_decision": "reject",
  "final_decision": "review",
  "reviewer": "成员姓名",
  "note": "需要确认敌方角色是否属于允许镜头",
  "downloads": {
    "csv": "/api/jobs/20260718_101530_a1b2c3d4/artifacts/detections.csv",
    "zip": "/api/jobs/20260718_101530_a1b2c3d4/artifacts/audit_package.zip"
  }
}
```

## 3. 接口

### `GET /health`

HTTP 200：

```json
{
  "ok": true,
  "status": "ok",
  "model_ready": false,
  "ffmpeg_ready": true,
  "storage_ready": true
}
```

`status` 表示 Flask 服务存活；三个 readiness 字段分别表达依赖状态，不能用静态常量冒充。

### `POST /jobs`

`multipart/form-data`：

| 字段 | 必填 | 规则 |
|---|---|---|
| `asset` | 是 | 单个合法媒体，最大 200MB |
| `project_name` | 是 | 去除首尾空格后 1–80 字 |
| `settings` | 否 | JSON 字符串，缺省使用默认规则 |

HTTP 201：

```json
{
  "ok": true,
  "job": {
    "job_id": "20260718_101530_a1b2c3d4",
    "status": "created"
  }
}
```

该接口只创建任务，不启动推理。

### `POST /jobs/<job_id>/analyze`

无请求体。仅允许 `created` 或 `failed` 任务。先持久化 `queued` 再返回。

HTTP 202：

```json
{
  "ok": true,
  "job_id": "20260718_101530_a1b2c3d4",
  "status": "queued"
}
```

`queued/running/completed` 重复请求返回 HTTP 409。

### `GET /jobs`

可选查询：`status=created|queued|running|completed|failed`。

HTTP 200：

```json
{
  "ok": true,
  "jobs": [],
  "total": 0
}
```

按 `created_at` 倒序。

### `GET /jobs/<job_id>`

HTTP 200 返回完整 `job`。不存在返回 404 `job_not_found`。

### `DELETE /jobs/<job_id>`

仅允许删除 `created/completed/failed`。成功 HTTP 200：

```json
{
  "ok": true,
  "deleted_job_id": "20260718_101530_a1b2c3d4"
}
```

`queued/running` 返回 HTTP 409 `job_busy`。

### `PATCH /jobs/<job_id>/review`

仅允许 `completed` 任务。

```json
{
  "decision": "review",
  "reviewer": "成员姓名",
  "note": "需要业务负责人确认"
}
```

`decision` 只允许 `pass | review | reject`；`reviewer` 去除空格后 1–40 字；`note` 最多 500 字。

HTTP 200 返回更新后的 `report`。必须保留原 `auto_decision`。

### `GET /jobs/<job_id>/report`

仅允许 `completed` 任务。HTTP 200：

```json
{
  "ok": true,
  "report": {}
}
```

### `GET /jobs/<job_id>/artifacts/<filename>`

`filename` 必须已出现在报告的证据或下载白名单中，只允许 basename。成功返回文件流；不存在或越界返回 404。

### `GET /stats`

HTTP 200：

```json
{
  "ok": true,
  "stats": {
    "total": 12,
    "pass": 5,
    "review": 4,
    "reject": 3,
    "failed": 1
  }
}
```

统计以最终结论为准；未人工改判时使用自动结论。

`total` 表示所有状态的任务总数。`pass/review/reject` 只统计
`completed` 报告，`failed` 单独统计失败任务，因此这些子项不要求简单相加
等于 `total`。

## 4. HTTP 状态

| 状态 | 用途 |
|---:|---|
| 200 | 查询、改判、删除成功 |
| 201 | 任务创建成功 |
| 202 | 分析已入队 |
| 400 | 参数、文件或规则错误 |
| 404 | 任务、产物或接口不存在 |
| 409 | 状态冲突或任务运行中 |
| 413 | 超过 200MB |
| 500 | 未预期服务错误；任务处理异常应优先写为 `failed` |
## 5. 错误码与 HTTP 状态映射

| 错误码 | HTTP 状态 | 说明 |
|---|---:|---|
| `invalid_request` | 400 | 请求参数错误 |
| `invalid_asset` | 400 | 素材文件格式不支持或无法解码 |
| `invalid_settings` | 400 | 审核规则参数错误 |
| `job_not_found` | 404 | 任务编号不存在 |
| `artifact_not_found` | 404 | 产物文件不存在或超出任务目录 |
| `not_found` | 404 | 请求的接口不存在 |
| `payload_too_large` | 413 | 上传文件超过 200MB 限制 |
| `job_busy` | 409 | 任务状态冲突或正在执行 |
| `internal_error` | 500 | 服务器内部错误，不暴露堆栈 |

所有错误响应结构：

```json
{
  "ok": false,
  "error": {
    "code": "machine_readable_code",
    "message": "用户可读中文说明"
  }
}
```

异常不会导致 Flask 进程退出，响应中不包含堆栈、绝对路径或模型内部对象。
