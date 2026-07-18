# QA Test Fixtures

所有夹具均由 `tests/fixtures/make_fixtures.py` 以固定随机种子生成，可重复调用得到完全相同的文件。

## 生成方法

```bash
# Docker（推荐——可使用 ffmpeg 生成视频）
docker compose build
docker compose run --rm -v .:/workspace app python tests/fixtures/make_fixtures.py

# 本地（仅图片——视频跳过）
python tests/fixtures/make_fixtures.py
```

## 文件清单

| 文件名 | 类型 | 来源 | 验证 SHA256（前 16 位） |
|---|---|---|---|
| `clean_scene.jpg` | 640×480 JPEG | Pillow 纯色背景（无 Risk 形状） | `c54a913c34f09698` |
| `risk_scene.jpg` | 640×480 JPEG | Pillow + 3 个小红色矩形 | `4c64e97c21879a43` |
| `reject_scene.jpg` | 640×480 JPEG | Pillow + 12 个大红色矩形 | `d6bc18c65b3b2e36` |
| `sample_5s.mp4` | 640×360 H.264 | lavfi testsrc + drawtext（5秒，24fps） | `6db8fe5a03db5734` |
| `corrupt.jpg` | 截断 JPEG | 有效 JPEG 头 + 512 字节零填充 | `4eabee9cb26afbf8` |
| `corrupt.mp4` | 随机字节 | LCG 随机字节（无有效容器魔数） | `145c33fcedaec30a` |
| `empty.bin` | 0 字节 | 空文件 | `e3b0c44298fc1c14` |
| `not_media.jpg` | 文本伪图片 | UTF-8 明文字符串 `.jpg` 伪装 | `0eacf80b6210a365` |

`manifest.json` 记录每个文件的最新 SHA256 散列。

所有图片均使用 RGB 模式、JPEG 质量 90 生成。视频使用 `libx264` 极速预设、无音频生成。

## 设计意图

- `clean_scene.jpg`：不含任何风险类目标形状，预期自动结论为 pass。
- `risk_scene.jpg`：仅包含少量小红色矩形，为中等风险场景。真实模型验收时需通过 CV 注入式假 detector 保证 review 确定性。
- `reject_scene.jpg`：大范围、高密度红色矩形，为高置信度风险场景。真实模型验收时需通过 CV 注入式假 detector 保证 reject 确定性。
- `sample_5s.mp4`：5 秒固定内容、每秒 24 帧，用于视频异步流程与证据帧测试。
- 损坏/空/误扩展文件：用于异常路径（A1–A3）验收。

## 版权声明

所有文件均为程序化生成，不包含第三方版权素材。
