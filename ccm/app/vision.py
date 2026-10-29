"""Vision pipeline: YOLOX-nano pet detection + eating detection.

Eating = pet inside the bowl ROI for >= N seconds AND bowl weight decreasing.
The detector code mirrors ai/benchmark_yolox.py (float ONNX model, CPU).
"""
from __future__ import annotations

from dataclasses import dataclass

COCO_IDS = {"bird": 14, "cat": 15, "dog": 16}  # 0-based COCO class ids used by YOLOX


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


class YoloxDetector:
    """YOLOX-nano on CPU (onnxruntime). Lazy imports so the backend runs without cv2/ort."""

    def __init__(self, model_path: str, conf: float = 0.4, classes: tuple[str, ...] = ("cat", "dog"),
                 threads: int = 0) -> None:
        import numpy as np
        import onnxruntime as ort

        self.np = np
        self.conf = conf
        self.wanted = {c: COCO_IDS[c] for c in classes}
        opts = ort.SessionOptions()
        if threads > 0:
            opts.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        self.input = self.sess.get_inputs()[0]
        self.size = self.input.shape[2] if isinstance(self.input.shape[2], int) else 416

    def _preprocess(self, img):
        """Letterbox to size x size (grey 114 padding). YOLOX: BGR, 0-255 floats."""
        cv2 = __import__("cv2")
        np = self.np
        h, w = img.shape[:2]
        r = min(self.size / h, self.size / w)
        nh, nw = int(h * r), int(w * r)
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((self.size, self.size, 3), 114, dtype=np.uint8)
        canvas[:nh, :nw] = resized
        blob = canvas.transpose(2, 0, 1)[None].astype(np.float32)
        return np.ascontiguousarray(blob), r

    def _decode(self, raw):
        np = self.np
        grids, strides = [], []
        for s in (8, 16, 32):
            n = self.size // s
            xv, yv = np.meshgrid(np.arange(n), np.arange(n))
            g = np.stack((xv, yv), 2).reshape(1, -1, 2)
            grids.append(g)
            strides.append(np.full((1, g.shape[1], 1), s))
        grids, strides = np.concatenate(grids, 1), np.concatenate(strides, 1)
        out = raw.copy()
        out[..., :2] = (out[..., :2] + grids) * strides
        out[..., 2:4] = np.exp(out[..., 2:4]) * strides
        return out[0]

    def detect(self, frame) -> list[Detection]:
        np = self.np
        blob, ratio = self._preprocess(frame)
        raw = self.sess.run(None, {self.input.name: blob})[0]
        pred = self._decode(raw)
        boxes_xywh, scores = pred[:, :4], pred[:, 4:5] * pred[:, 5:]
        results: list[Detection] = []
        for label, cid in self.wanted.items():
            sc = scores[:, cid]
            m = sc > self.conf
            if not m.any():
                continue
            b, s = boxes_xywh[m], sc[m]
            xyxy = (
                np.stack(
                    [b[:, 0] - b[:, 2] / 2, b[:, 1] - b[:, 3] / 2,
                     b[:, 0] + b[:, 2] / 2, b[:, 1] + b[:, 3] / 2],
                    1,
                )
                / ratio
            )
            for i in _nms(xyxy, s, 0.45):
                x1, y1, x2, y2 = (float(v) for v in xyxy[i])
                results.append(Detection(label, float(s[i]), (int(x1), int(y1), int(x2), int(y2))))
        return results


def _nms(boxes, scores, thr):
    import numpy as np

    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(i)
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        area_r = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        order = rest[inter / (area_i + area_r - inter + 1e-9) <= thr]
    return keep
