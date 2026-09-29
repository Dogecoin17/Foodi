"""Vision pipeline stub (Phase 6).

Plan: pretrained nano detector (YOLO-nano / MobileNet-SSD, int8) at 1-2 fps.
Eating = pet inside the bowl ROI for >= N seconds AND bowl weight decreasing.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Detection:
    label: str  # "cat" | "dog"
    confidence: float
    box: tuple[int, int, int, int]  # x1, y1, x2, y2


class EatingDetector:
    def __init__(self, roi: tuple[int, int, int, int], min_seconds: float = 5.0) -> None:
        self.roi = roi
        self.min_seconds = min_seconds
        self._in_roi_since: float | None = None

    def update(self, detections: list[Detection], now: float, bowl_weight_falling: bool) -> bool:
        """Feed one inference result; returns True while the pet is judged to be eating."""
        in_roi = any(self._overlaps(d.box) for d in detections if d.label in ("cat", "dog"))
        if not in_roi:
            self._in_roi_since = None
            return False
        if self._in_roi_since is None:
            self._in_roi_since = now
        return (now - self._in_roi_since) >= self.min_seconds and bowl_weight_falling

    def _overlaps(self, box: tuple[int, int, int, int]) -> bool:
        ax1, ay1, ax2, ay2 = self.roi
        bx1, by1, bx2, by2 = box
        return not (bx2 < ax1 or bx1 > ax2 or by2 < ay1 or by1 > ay2)
