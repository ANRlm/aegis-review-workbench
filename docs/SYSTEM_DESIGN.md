# 影鉴 Aegis Review 系统设计

## 1. 架构选择

系统使用 Flask 模块化单体、单进程后台线程池和本地文件持久化。该结构满足一天开发、Docker 单服务、JSON 数据层和五人并行要求，并避免为课程项目引入 Redis、数据库或 Celery。

```text
浏览器
  │ HTTP + 轮询
  ▼
Flask API ── JobService ── ThreadPoolExecutor(max_workers=1)
  │              │                      │
  │              ▼                      ▼
  │         JobStorage            CV Pipeline
  │              │             OpenCV → YOLO → Rules
  └──────────────┴──────────────────────┘
                 │
                 ▼
          outputs/<job_id>/
```

## 2. 模块职责

| 模块 | 职责 | 不负责 |
|---|---|---|
| `config.py` | 根目录、上传上限、模型与输出路径 | 业务状态 |
| `domain.py` | 状态、结论、规则、报告类型 | Flask 和磁盘 I/O |
| `storage.py` | 原子 JSON、任务目录、安全路径与删除 | 推理和 HTTP |
| `service.py` | 状态机、锁、线程池、重启恢复 | 文件解码 |
| `api.py` | 请求解析、状态码、错误响应、文件响应 | 审核规则 |
| `cv/` | 采样、检测、规则、证据和产物 | HTTP 与任务列表 |
| `templates/static` | 工作台与 API 交互 | 自行推导后端状态 |

应用工厂只创建一个 `JobService`，启动时完成遗留任务恢复，并将实例注册到：

```python
app.extensions["aegis_job_service"]
```

后端路由只能消费该实例，不得在 `api.py` 中创建第二个线程池或复制状态机。
组长核心通过已绑定检测器的 `AnalysisRunner` 调用 CV 管线；CV 合入前使用明确
报错的不可用实现，使 Flask 可以启动而分析任务留下可重试的失败记录。

## 3. 数据流

### 创建与分析

1. `POST /api/jobs` 校验 multipart 字段、扩展名、大小和可解码性。
2. 服务生成 `YYYYMMDD_HHMMSS_<8hex>` 任务 ID。
3. 原素材使用固定安全文件名保存，创建 `job.json`，状态为 `created`。
4. `POST /api/jobs/<id>/analyze` 在任务锁内验证状态，先写入 `queued`，再提交线程池并返回 HTTP 202。
5. 工作线程写入 `running` 和 `started_at`，调用 CV 管线。
6. CV 管线输出证据、JSON、CSV 和 ZIP。
7. 成功写入 `completed/completed_at/result_file`；任何异常写入 `failed/completed_at/error`。

### 查询与人工审核

前端每秒查询任务详情；到达 `completed/failed` 后停止轮询。人工改判只修改报告中的 `final_decision/reviewer/note`，不改变任务状态或覆盖 `auto_decision`。

任务详情中的 `asset_url` 由后端根据 `asset_file` 派生，并复用安全产物接口
读取 `input/original.<ext>`；客户端不能提交或拼接磁盘路径。

## 4. 并发与持久化

- 线程池固定一个 worker，避免 CPU 上同时加载多次 YOLO。
- 每个任务一个内存锁，修改前重新读取磁盘状态。
- JSON 先写同目录 `.tmp`，`flush + fsync` 后原子替换。
- 列表接口从磁盘读取，因此刷新或重启后仍可打开历史任务。
- 启动时扫描 `queued/running`，将其标记为 `failed`，错误为“服务中断，任务未完成”；失败任务允许重新进入 `queued`。
- 正在 `queued/running` 的任务不能删除。

## 5. 文件安全

- 任务 ID 必须匹配 `^\d{8}_\d{6}_[0-9a-f]{8}$`。
- 上传不使用用户原始文件名作为磁盘路径，只保留清洗后的展示名称。
- 产物下载只接受报告白名单中的 basename，不接受 `/`、`\`、`..` 或符号链接。
- 删除前解析真实路径并确认仍位于 `outputs` 下。
- 错误响应不返回本机绝对路径、堆栈或环境变量。

## 6. CV 设计

模型以 `yolo11n.pt` 为初始权重，在已有 96 张训练、24 张验证的五类游戏数据上重新训练 30 epoch。类别顺序固定为：

```text
player, enemy, energy_orb, treasure_chest, health_potion
```

图片产生一个采样帧。视频使用 OpenCV 获取 FPS 和总帧数，按 `sample_interval_seconds` 跳帧，最多处理 `max_sample_frames`。检测适配器将 Ultralytics 对象立即转换为纯 Python 字典，其他模块不依赖 Ultralytics 内部类型。

证据按规则相关度、置信度和时间排序，至少保留 `min_evidence_frames` 张。无目标时保存第一个原始代表帧。

## 7. 运行环境

Docker 镜像基于 Python 3.11 slim，安装 FFmpeg、Node.js 和中文字体；项目依赖固定在 `requirements.txt`。容器将 `outputs` 绑定为可写目录、`models` 绑定为只读目录。Conda 环境仅用于本地开发，名称固定为 `aegis-review`。

Flask 单进程启动是线程任务模型的约束；不得使用多个 Gunicorn worker，否则不同进程会维护不一致的任务锁和线程池。
