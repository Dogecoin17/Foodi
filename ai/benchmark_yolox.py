#!/usr/bin/env python3
"""YOLOX-Nano benchmark for Foodi: speed, CPU, memory and pet detections on a video.

Works on a PC first; the same script runs on the UNO Q later (pip install the same packages).
Example:
  python benchmark_yolox.py --model yolox_nano.onnx --video clips/bowl1.mp4 --stride 5 --csv results.csv --save out.mp4

NOTE: this uses the original float ONNX model. The model bundled with Arduino App Lab is a
quantized Edge Impulse build, so treat PC accuracy as an upper bound and PC speed as relative only.
"""
import argparse
import csv
import glob
import os
import statistics
import time

import cv2
import numpy as np
import onnxruntime as ort
import psutil

COCO_IDS = {"bird": 14, "cat": 15, "dog": 16}  # 0-based COCO class ids used by YOLOX


def preprocess(img, size):
    """Letterbox to size x size (grey 114 padding). YOLOX expects BGR, 0-255 floats, no normalisation."""
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    nh, nw = int(h * r), int(w * r)
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    canvas[:nh, :nw] = resized
    blob = canvas.transpose(2, 0, 1)[None].astype(np.float32)
    return np.ascontiguousarray(blob), r


def decode(raw, size):
    """Turn raw YOLOX output (1, N, 85) into pixel-space boxes (centre x, y, w, h, obj, 80 class scores)."""
    grids, strides = [], []
    for s in (8, 16, 32):
        n = size // s
        xv, yv = np.meshgrid(np.arange(n), np.arange(n))
        g = np.stack((xv, yv), 2).reshape(1, -1, 2)
        grids.append(g)
        strides.append(np.full((1, g.shape[1], 1), s))
    grids, strides = np.concatenate(grids, 1), np.concatenate(strides, 1)
    out = raw.copy()
    out[..., :2] = (out[..., :2] + grids) * strides
    out[..., 2:4] = np.exp(out[..., 2:4]) * strides
    return out[0]


def nms(boxes, scores, thr):
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


def detect(pred, ratio, conf, wanted, nms_thr=0.45):
    """Return [(label, score, (x1, y1, x2, y2))] in original-image pixels for the wanted classes."""
    boxes_xywh, scores = pred[:, :4], pred[:, 4:5] * pred[:, 5:]
    results = []
    for label, cid in wanted.items():
        sc = scores[:, cid]
        m = sc > conf
        if not m.any():
            continue
        b, s = boxes_xywh[m], sc[m]
        xyxy = np.stack([b[:, 0] - b[:, 2] / 2, b[:, 1] - b[:, 3] / 2,
                         b[:, 0] + b[:, 2] / 2, b[:, 1] + b[:, 3] / 2], 1) / ratio
        for i in nms(xyxy, s, nms_thr):
            results.append((label, float(s[i]), tuple(float(v) for v in xyxy[i])))
    return results


def read_temp_c():
    """Hottest thermal zone in deg C (Linux/UNO Q only; None on Windows)."""
    temps = []
    for p in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            temps.append(int(open(p).read().strip()) / 1000)
        except (OSError, ValueError):
            pass
    return max(temps) if temps else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--video", required=True, help="video file, MJPEG/RTSP URL, or camera index")
    ap.add_argument("--size", type=int, default=416, help="input size (nano default 416)")
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--stride", type=int, default=1, help="process every Nth frame (emulates a low AI frame rate)")
    ap.add_argument("--threads", type=int, default=0, help="inference threads (0 = default; use 4 to mimic the UNO Q)")
    ap.add_argument("--classes", nargs="+", default=["cat", "dog"], choices=list(COCO_IDS))
    ap.add_argument("--no-spin", action="store_true",
                    help="stop ONNX worker threads busy-waiting between frames (lower idle CPU load)")
    ap.add_argument("--roi", help="bowl region as normalised x1,y1,x2,y2 (0-1), drawn on the saved video")
    ap.add_argument("--roi-margin", type=float, default=0.05,
                    help="extra margin around the ROI that counts as 'near the bowl' (drawn as a thin box)")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--csv")
    ap.add_argument("--save", help="write an annotated video here")
    a = ap.parse_args()

    opts = ort.SessionOptions()
    if a.threads:
        opts.intra_op_num_threads = a.threads
    if a.no_spin:
        opts.add_session_config_entry("session.intra_op.allow_spinning", "0")
    roi = None
    if a.roi:
        roi = [float(v) for v in a.roi.split(",")]
        if len(roi) != 4 or not all(0 <= v <= 1 for v in roi) or roi[0] >= roi[2] or roi[1] >= roi[3]:
            raise SystemExit("--roi must be four numbers 0-1: x1,y1,x2,y2 with x1<x2 and y1<y2")
    sess = ort.InferenceSession(a.model, opts, providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    if isinstance(inp.shape[2], int):
        a.size = inp.shape[2]
    wanted = {c: COCO_IDS[c] for c in a.classes}

    for out_path in (a.save, a.csv):
        if out_path and os.path.dirname(out_path):
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
    src = int(a.video) if a.video.isdigit() else a.video
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f"Cannot open video source: {a.video}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    ok, frame = cap.read()
    if not ok:
        raise SystemExit("Video has no frames")
    blob, _ = preprocess(frame, a.size)
    for _ in range(5):  # warm-up, not counted
        sess.run(None, {inp.name: blob})

    writer = None
    if a.save:
        h, w = frame.shape[:2]
        writer = cv2.VideoWriter(a.save, cv2.VideoWriter_fourcc(*"mp4v"), max(1.0, src_fps / a.stride), (w, h))

    proc = psutil.Process()
    cpu0, wall0 = sum(proc.cpu_times()[:2]), time.perf_counter()
    peak_rss, peak_temp = 0, read_temp_c()
    inf_ms, tot_ms, rows = [], [], []
    pet_frames, idx, processed = 0, -1, 0

    while ok:
        idx += 1
        if idx % a.stride == 0:
            t0 = time.perf_counter()
            blob, ratio = preprocess(frame, a.size)
            t1 = time.perf_counter()
            raw = sess.run(None, {inp.name: blob})[0]
            t2 = time.perf_counter()
            dets = detect(decode(raw, a.size), ratio, a.conf, wanted)
            t3 = time.perf_counter()

            inf_ms.append((t2 - t1) * 1000)
            tot_ms.append((t3 - t0) * 1000)
            processed += 1
            pet_frames += bool(dets)
            best = max(dets, key=lambda d: d[1]) if dets else None
            fh, fw = frame.shape[:2]
            box = [round(v, 1) for v in best[2]] if best else ["", "", "", ""]
            rows.append([idx, round(idx / src_fps, 2), round(inf_ms[-1], 1), len(dets),
                         best[0] if best else "", round(best[1], 3) if best else "", *box, fw, fh])
            peak_rss = max(peak_rss, proc.memory_info().rss)
            if processed % 20 == 0:
                t = read_temp_c()
                peak_temp = max(peak_temp, t) if (t is not None and peak_temp is not None) else (t or peak_temp)
            if writer:
                if roi:
                    m = a.roi_margin
                    ex = [max(0, roi[0] - m), max(0, roi[1] - m), min(1, roi[2] + m), min(1, roi[3] + m)]
                    cv2.rectangle(frame, (int(ex[0] * fw), int(ex[1] * fh)), (int(ex[2] * fw), int(ex[3] * fh)), (0, 165, 255), 1)
                    cv2.rectangle(frame, (int(roi[0] * fw), int(roi[1] * fh)), (int(roi[2] * fw), int(roi[3] * fh)), (255, 120, 0), 2)
                for label, score, (x1, y1, x2, y2) in dets:
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 200, 0), 2)
                    cv2.putText(frame, f"{label} {score:.2f}", (int(x1), max(15, int(y1) - 5)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 0), 2)
                writer.write(frame)
            if a.max_frames and processed >= a.max_frames:
                break
        ok, frame = cap.read()

    wall = time.perf_counter() - wall0
    cpu = sum(proc.cpu_times()[:2]) - cpu0
    cap.release()
    if writer:
        writer.release()
    if not processed:
        raise SystemExit("No frames processed")

    p95 = sorted(tot_ms)[int(0.95 * (len(tot_ms) - 1))]
    print("\n=== Foodi detector benchmark ===")
    print(f"model: {a.model}   input: {a.size}px   threads: {a.threads or 'default'}   no-spin: {'on' if a.no_spin else 'off'}   classes: {', '.join(a.classes)}")
    print(f"frames processed: {processed} (every {a.stride}th of {idx + 1} video frames)")
    print(f"inference only:  mean {statistics.mean(inf_ms):.1f} ms   median {statistics.median(inf_ms):.1f} ms")
    print(f"full pipeline:   mean {statistics.mean(tot_ms):.1f} ms   p95 {p95:.1f} ms")
    print(f"max sustainable rate: {1000 / statistics.mean(tot_ms):.1f} fps (pipeline, one frame at a time)")
    print(f"CPU use: {100 * cpu / wall:.0f}% of one core while running (includes video decoding)")
    print(f"peak memory: {peak_rss / 1e6:.0f} MB")
    print(f"pet found in {pet_frames}/{processed} frames ({100 * pet_frames / processed:.0f}%)")
    if peak_temp is not None:
        print(f"hottest thermal zone: {peak_temp:.0f} C")
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["frame", "video_time_s", "inference_ms", "n_pets", "best_label", "best_conf",
                        "x1", "y1", "x2", "y2", "frame_w", "frame_h"])
            w.writerows(rows)
        print(f"per-frame results: {a.csv}")


if __name__ == "__main__":
    main()
