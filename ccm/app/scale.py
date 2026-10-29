"""Seven-segment LCD reader for the kitchen-scale display (SilverCrest).

No ML: crop the display region, threshold (digits are dark on light LCD),
find digit blobs, decode each by checking which of the 7 segments are lit.
Assumes a fixed, roughly frontal camera; the ROI is configured once in frame
pixels via FOODI_SCALE_ROI=x1,y1,x2,y2.
"""
from __future__ import annotations

# Relative sampling regions of each segment inside a digit's bounding box
# (x1, y1, x2, y2) as fractions of the digit's width/height.
SEGMENTS = {
    "a": (0.25, 0.00, 0.75, 0.18),
    "b": (0.72, 0.10, 1.00, 0.45),
    "c": (0.72, 0.55, 1.00, 0.90),
    "d": (0.25, 0.82, 0.75, 1.00),
    "e": (0.00, 0.55, 0.28, 0.90),
    "f": (0.00, 0.10, 0.28, 0.45),
    "g": (0.25, 0.42, 0.75, 0.58),
}

DIGIT_SEGMENTS = {
    0: "abcdef",
    1: "bc",
    2: "abdeg",
    3: "abcdg",
    4: "bcfg",
    5: "acdfg",
    6: "acdefg",
    7: "abc",
    8: "abcdefg",
    9: "abcdfg",
}
_BY_SEGMENTS = {frozenset(v): k for k, v in DIGIT_SEGMENTS.items()}

SEGMENT_ON_RATIO = 0.45  # fraction of lit pixels for a segment to count as on
UPSCALE = 3


def _classify_digit(blob) -> int | None:
    """blob: thresholded image of one digit (digit = white on black)."""
    h, w = blob.shape
    if w < 0.35 * h:
        return 1  # only "1" is a narrow bar pair; full-cell sampling would misread it
    lit = set()
    for seg, (fx1, fy1, fx2, fy2) in SEGMENTS.items():
        region = blob[int(fy1 * h):max(int(fy2 * h), 1), int(fx1 * w):max(int(fx2 * w), 1)]
        if region.size == 0:
            continue
        if (region > 0).mean() >= SEGMENT_ON_RATIO:
            lit.add(seg)
    if frozenset(lit) in _BY_SEGMENTS:
        return _BY_SEGMENTS[frozenset(lit)]
    # tolerate one misread segment: nearest pattern by symmetric difference
    best, best_dist = None, 3
    for pattern, digit in _BY_SEGMENTS.items():
        dist = len(lit ^ pattern)
        if dist < best_dist:
            best, best_dist = digit, dist
    return best


def read_grams(frame, roi: tuple[int, int, int, int]) -> int | None:
    """Read the scale display inside roi=(x1,y1,x2,y2). Returns grams or None."""
    import cv2

    x1, y1, x2, y2 = roi
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=UPSCALE, fy=UPSCALE, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    # digits are darker than the LCD background -> white blobs on black
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)))
    # Find blobs on a dilated copy (a digit's segments don't always touch:
    # "0" splits in two, "1" is two bars) but classify on the clean image.
    h_roi = bw.shape[0]
    kw, kh = max(3, int(0.03 * h_roi)), max(3, int(0.12 * h_roi))
    merged = cv2.dilate(bw, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kw, kh)))

    blobs = []
    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # undo the dilation margin to approximate the original digit extent
        x, y = x + kw // 2, y + kh // 2
        w, h = w - kw, h - kh
        if w <= 0 or h <= 0:
            continue
        if h < 0.35 * h_roi or h > 0.95 * h_roi:  # digits span most of the display height
            continue
        if not (0.1 * h < w < 0.85 * h):  # digit aspect, filters the "g" unit mark
            continue
        blobs.append((x, y, w, h))
    blobs.sort()
    if not 1 <= len(blobs) <= 4:
        return None

    digits = []
    for x, y, w, h in blobs:
        pad = int(0.05 * h)
        blob = bw[max(y - pad, 0):y + h + pad, max(x - pad, 0):x + w + pad]
        d = _classify_digit(blob)
        if d is None:
            return None
        digits.append(d)
    value = 0
    for d in digits:
        value = value * 10 + d
    return value
