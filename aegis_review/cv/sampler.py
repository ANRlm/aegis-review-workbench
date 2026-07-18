"""Image and video frame sampling helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from aegis_review.cv.exceptions import MediaDecodeError


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}
DEFAULT_FPS = 25.0


@dataclass(frozen=True, slots=True)
class SampledFrame:
    frame_index: int
    timestamp_seconds: float
    image: np.ndarray


def _read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        raise MediaDecodeError(f"无法解码图片：文件为空（{path.name}）。")
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise MediaDecodeError(f"无法解码图片：{path.name}。")
    return image


def sample_media(
    input_path: Path,
    *,
    sample_interval_seconds: float,
    max_sample_frames: int,
) -> list[SampledFrame]:
    """Decode an image or time-sample a video into BGR frames."""
    if sample_interval_seconds <= 0:
        raise ValueError("sample_interval_seconds must be positive")
    if max_sample_frames < 1:
        raise ValueError("max_sample_frames must be at least 1")

    path = Path(input_path)
    if not path.is_file():
        raise MediaDecodeError(f"媒体文件不存在：{path.name}。")

    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        image = _read_image(path)
        return [
            SampledFrame(frame_index=0, timestamp_seconds=0.0, image=image),
        ]
    if suffix not in VIDEO_EXTENSIONS:
        raise MediaDecodeError(f"不支持的媒体类型：{path.name}。")

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise MediaDecodeError(f"无法打开视频：{path.name}。")

    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        if not np.isfinite(fps) or fps <= 0:
            fps = DEFAULT_FPS
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if frame_count <= 0:
            raise MediaDecodeError(f"视频缺少有效帧：{path.name}。")

        interval_frames = max(1, int(round(fps * sample_interval_seconds)))
        selected_indices: list[int] = []
        index = 0
        while index < frame_count and len(selected_indices) < max_sample_frames:
            selected_indices.append(index)
            index += interval_frames

        frames: list[SampledFrame] = []
        for target in selected_indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, target)
            ok, image = capture.read()
            if not ok or image is None:
                raise MediaDecodeError(
                    f"视频帧读取失败：{path.name} @ frame {target}。"
                )
            timestamp = target / fps
            frames.append(
                SampledFrame(
                    frame_index=int(target),
                    timestamp_seconds=float(timestamp),
                    image=image,
                )
            )
        if not frames:
            raise MediaDecodeError(f"视频没有可采样帧：{path.name}。")
        return frames
    finally:
        capture.release()
