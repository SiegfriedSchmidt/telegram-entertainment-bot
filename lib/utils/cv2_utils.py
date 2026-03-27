import numpy as np


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
