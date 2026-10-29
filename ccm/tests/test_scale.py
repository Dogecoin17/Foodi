"""Seven-segment scale-display decoding, tested on synthesized LCD frames."""
import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from app.scale import DIGIT_SEGMENTS, SEGMENTS, read_grams  # noqa: E402

W, H = 50, 90


def _draw_digit(canvas, digit, ox, oy):
    for seg in DIGIT_SEGMENTS[digit]:
        fx1, fy1, fx2, fy2 = SEGMENTS[seg]
        cv2.rectangle(
            canvas,
            (ox + int(fx1 * W), oy + int(fy1 * H)),
            (ox + int(fx2 * W), oy + int(fy2 * H)),
            0,
            -1,
        )


def _frame(number: int):
    s = str(number)
    img = np.full((200, 120 + len(s) * 70, 3), 210, np.uint8)
    for i, ch in enumerate(s):
        _draw_digit(img, int(ch), 30 + i * 70, 50)
    return img


@pytest.mark.parametrize(
    "n", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 42, 99, 135, 250, 1000]
)
def test_read_grams_synthetic(n):
    img = _frame(n)
    assert read_grams(img, (0, 0, img.shape[1], img.shape[0])) == n


def test_read_grams_empty_roi():
    assert read_grams(np.zeros((100, 100, 3), np.uint8), (10, 10, 20, 20)) is None
