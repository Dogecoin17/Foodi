"""Live video pipeline: phone/ESP32 MJPEG stream -> AI overlay -> dashboard.

The source URL (FOODI_VIDEO_URL) is anything OpenCV can open: the phone app
(e.g. IP Webcam's http://<phone-ip>:8080/video), an ESP32-S3 stream, a USB
camera index, or a video file (useful for rehearsing without the phone).

A background thread grabs frames, runs the YOLOX detector (if available),
judges "eating" from pet-in-ROI + falling bowl weight, annotates, and keeps
the latest JPEG. /api/video re-serves it as multipart/x-mixed-replace.
The AI is best-effort: if the model or cv2 is missing, the raw stream passes
through unchanged. If the source drops, the thread reconnects with backoff.
"""
from __future__ import annotations

import logging
import statistics
import threading
import time
from collections.abc import Callable

from .scale import read_grams
from .vision import EatingDetector, YoloxDetector

log = logging.getLogger(__name__)

JPEG_QUALITY = 70
DETECT_EVERY = 2  # run inference on every Nth frame
RECONNECT_S = 2.0


class VideoPipeline:
    def __init__(
        self,
        url: str,
        model_path: str = "",
        weight_provider: Callable[[], float | None] = lambda: None,
        scale_roi: tuple[int, int, int, int] | None = None,
        scale_callback: Callable[[int], None] | None = None,
        detector_threads: int = 0,
    ) -> None:
        self.url = url
        self.model_path = model_path
        self.detector_threads = detector_threads
        self.weight_provider = weight_provider
        self.scale_roi = scale_roi
        self.scale_callback = scale_callback
        self._jpeg: bytes | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.eating = False
        self.scale_weight: int | None = None
        self._scale_votes: list[int] = []
        self._weights: list[tuple[float, float]] = []  # (ts, grams) for the falling check
        self.detections_done = 0
        self.infer_ms_total = 0.0
        self.started_at: float | None = None

    @property
    def avg_infer_ms(self) -> float | None:
        return self.infer_ms_total / self.detections_done if self.detections_done else None

    @property
    def detect_fps(self) -> float | None:
        if not self.started_at or not self.detections_done:
            return None
        return self.detections_done / (time.time() - self.started_at)

    def start(self) -> None:
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._run, name="video", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._jpeg

    # ---- internals ------------------------------------------------------------
    def _read_scale(self, frame, detections) -> None:
        x1, y1, x2, y2 = self.scale_roi
        for d in detections:
            bx1, by1, bx2, by2 = d.box
            if not (bx2 < x1 or bx1 > x2 or by2 < y1 or by1 > y2):
                return  # pet is blocking the display; hold the last reading
        grams = read_grams(frame, self.scale_roi)
        if grams is None:
            return
        self._scale_votes.append(grams)
        del self._scale_votes[:-5]
        voted = int(statistics.median(self._scale_votes))
        if voted != self.scale_weight:
            self.scale_weight = voted
            now = time.time()
            self._weights.append((now, voted))
            self._weights = [(t, x) for t, x in self._weights if now - t < 10.0]
            if self.scale_callback:
                try:
                    self.scale_callback(voted)
                except Exception as exc:
                    log.warning("scale callback failed: %s", exc)

    def _weight_falling(self) -> bool:
        if self.scale_weight is None:
            w = self.weight_provider()
            now = time.time()
            if w is not None:
                self._weights.append((now, w))
                self._weights = [(t, x) for t, x in self._weights if now - t < 10.0]
        if len(self._weights) < 3:
            return False
        return self._weights[0][1] - self._weights[-1][1] > 1.0  # lost >1 g in ~10 s

    def _make_detector(self) -> YoloxDetector | None:
        if not self.model_path:
            return None
        try:
            det = YoloxDetector(self.model_path, threads=self.detector_threads)
            log.info("video AI enabled: %s", self.model_path)
            return det
        except Exception as exc:
            log.warning("video AI disabled (%s); passing the raw stream through", exc)
            return None

    def _run(self) -> None:
        import cv2

        detector = self._make_detector()
        eater = EatingDetector(roi=(0, 0, 10_000, 10_000), min_seconds=5.0)  # whole frame
        frame_idx = 0
        detections: list = []

        while not self._stop.is_set():
            src = int(self.url) if self.url.isdigit() else self.url
            cap = cv2.VideoCapture(src)
            if not cap.isOpened():
                log.warning("video source %s unavailable; retrying in %ss", self.url, RECONNECT_S)
                time.sleep(RECONNECT_S)
                continue
            log.info("video source connected: %s", self.url)

            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    log.warning("video source dropped; reconnecting")
                    break
                frame_idx += 1

                if frame_idx % DETECT_EVERY == 0:
                    if detector:
                        t0 = time.perf_counter()
                        try:
                            detections = detector.detect(frame)
                        except Exception as exc:
                            log.warning("detection failed: %s", exc)
                            detections = []
                        self.infer_ms_total += (time.perf_counter() - t0) * 1000
                        self.detections_done += 1
                        self.eating = eater.update(detections, time.time(), self._weight_falling())
                    if self.scale_roi:
                        self._read_scale(frame, detections)

                if detector or self.scale_roi:
                    self._annotate(cv2, frame, detections)

                ok_enc, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                if ok_enc:
                    with self._lock:
                        self._jpeg = buf.tobytes()
                time.sleep(0.03)  # ~30 fps ceiling; the endpoint throttles further

            cap.release()
            if not self._stop.is_set():
                time.sleep(RECONNECT_S)

    def _annotate(self, cv2, frame, detections) -> None:
        if self.scale_roi:
            x1, y1, x2, y2 = self.scale_roi
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 200), 2)
            label = f"{self.scale_weight} g" if self.scale_weight is not None else "-- g"
            cv2.putText(frame, label, (x1, max(15, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 200), 2)
        for d in detections:
            x1, y1, x2, y2 = d.box
            color = (0, 200, 0) if not self.eating else (0, 0, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{d.label} {d.confidence:.2f}", (x1, max(15, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        if self.eating:
            cv2.putText(frame, "EATING", (10, 40), cv2.FONT_HERSHEY_SIMPLEX,
                        1.2, (0, 0, 255), 3)
