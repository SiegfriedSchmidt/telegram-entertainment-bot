import subprocess
import cv2
import numpy as np
from lib.storage import storage
from pathlib import Path
from random import randint


def cv2_paste_with_alpha(background: np.ndarray, foreground: np.ndarray, pos: tuple[int, int]) -> None:
    x, y = pos
    fg_h, fg_w = foreground.shape[:2]
    roi = background[y:y + fg_h, x:x + fg_w]

    if foreground.shape[2] == 4:
        alpha = foreground[:, :, 3] / 255.0
        for c in range(3):
            roi[:, :, c] = (1 - alpha) * roi[:, :, c] + alpha * foreground[:, :, c]
    else:
        roi[:] = foreground

    background[y:y + fg_h, x:x + fg_w] = roi


class OpencvCustomWriter:
    def __init__(self, fps: int, width: int, height: int, filename: str):
        self.fps = fps
        self.width = width
        self.height = height
        self.filename = filename
        self.writer: cv2.VideoWriter | None = None
        self.video_temp: Path | None = None

    def __enter__(self) -> cv2.VideoWriter:
        if storage.ffmpeg_use:
            self.video_temp = Path(self.filename).parent / f"temp_{randint(0, 1 << 31)}.mkv"
            self.writer = cv2.VideoWriter(self.video_temp, cv2.VideoWriter.fourcc(*'MJPG'), self.fps,
                                          (self.width, self.height))
        else:
            self.writer = cv2.VideoWriter(self.filename, cv2.VideoWriter.fourcc(*'avc1'), self.fps,
                                          (self.width, self.height))

        return self.writer

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.writer.release()
        self.writer = None

        if self.video_temp is not None:
            subprocess.run([
                'ffmpeg', '-y', '-i', self.video_temp,
                '-c:v', 'libx264', '-crf', str(storage.ffmpeg_crf), '-preset', storage.ffmpeg_preset,
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                # '-c:a', 'aac', '-b:a', '128k',
                self.filename
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.video_temp.unlink()
