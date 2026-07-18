from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from aegis_review.cv.exceptions import MediaDecodeError
from aegis_review.cv.sampler import sample_media


def _write_image(path: Path, color: tuple[int, int, int] = (40, 80, 120)) -> None:
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    image[:] = color
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    encoded.tofile(str(path))


def _write_video(
    path: Path,
    *,
    frame_count: int,
    fps: float,
) -> None:
    width, height = 64, 48
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps if fps > 0 else 25.0, (width, height))
    assert writer.isOpened()
    for index in range(frame_count):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (index * 3) % 255
        writer.write(frame)
    writer.release()


def test_image_samples_single_frame(tmp_path: Path) -> None:
    image_path = tmp_path / "frame.jpg"
    _write_image(image_path)
    frames = sample_media(
        image_path,
        sample_interval_seconds=1.0,
        max_sample_frames=120,
    )
    assert len(frames) == 1
    assert frames[0].frame_index == 0
    assert frames[0].timestamp_seconds == 0.0
    assert frames[0].image.shape[0] == 48


def test_video_samples_by_interval_and_variable_fps(tmp_path: Path) -> None:
    video_path = tmp_path / "clip.mp4"
    _write_video(video_path, frame_count=50, fps=10.0)
    frames = sample_media(
        video_path,
        sample_interval_seconds=1.0,
        max_sample_frames=120,
    )
    # 10 fps * 1s = every 10 frames → indices 0,10,20,30,40
    assert [frame.frame_index for frame in frames] == [0, 10, 20, 30, 40]
    assert frames[1].timestamp_seconds == pytest.approx(1.0)


def test_sample_interval_half_second(tmp_path: Path) -> None:
    video_path = tmp_path / "half.mp4"
    _write_video(video_path, frame_count=30, fps=10.0)
    frames = sample_media(
        video_path,
        sample_interval_seconds=0.5,
        max_sample_frames=120,
    )
    assert [frame.frame_index for frame in frames] == [0, 5, 10, 15, 20, 25]


def test_max_sample_frames_cap_at_120(tmp_path: Path) -> None:
    video_path = tmp_path / "long.mp4"
    _write_video(video_path, frame_count=400, fps=1.0)
    frames = sample_media(
        video_path,
        sample_interval_seconds=1.0,
        max_sample_frames=120,
    )
    assert len(frames) == 120
    assert frames[-1].frame_index == 119


def test_missing_fps_uses_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video_path = tmp_path / "nofps.mp4"
    _write_video(video_path, frame_count=60, fps=25.0)

    class FakeCapture:
        def __init__(self, *_args, **_kwargs) -> None:
            self._index = -1
            self._frames = [
                np.full((48, 64, 3), fill_value=i, dtype=np.uint8) for i in range(60)
            ]

        def isOpened(self) -> bool:
            return True

        def get(self, prop: int) -> float:
            if prop == cv2.CAP_PROP_FPS:
                return 0.0
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return float(len(self._frames))
            return 0.0

        def set(self, _prop: int, value: float) -> bool:
            self._index = int(value) - 1
            return True

        def read(self):
            self._index += 1
            if self._index < 0 or self._index >= len(self._frames):
                return False, None
            return True, self._frames[self._index]

        def release(self) -> None:
            return None

    monkeypatch.setattr(cv2, "VideoCapture", FakeCapture)
    frames = sample_media(
        video_path,
        sample_interval_seconds=1.0,
        max_sample_frames=120,
    )
    # default fps 25 → interval 25 frames
    assert [frame.frame_index for frame in frames] == [0, 25, 50]
    assert frames[1].timestamp_seconds == pytest.approx(1.0)


def test_corrupt_video_raises_readable_error(tmp_path: Path) -> None:
    video_path = tmp_path / "bad.mp4"
    video_path.write_bytes(b"not-a-video")
    with pytest.raises(MediaDecodeError, match="无法打开视频|视频"):
        sample_media(
            video_path,
            sample_interval_seconds=1.0,
            max_sample_frames=120,
        )


def test_corrupt_image_raises_readable_error(tmp_path: Path) -> None:
    image_path = tmp_path / "bad.jpg"
    image_path.write_bytes(b"xxxx")
    with pytest.raises(MediaDecodeError, match="无法解码图片"):
        sample_media(
            image_path,
            sample_interval_seconds=1.0,
            max_sample_frames=120,
        )
