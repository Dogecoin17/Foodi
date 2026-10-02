#!/usr/bin/env python3
"""Turn a benchmark CSV into 'eating' intervals and (optionally) score them against your own notes.

Rule (vision half only): a pet counts as 'at the bowl' when its box touches the bowl region
(plus a margin). Short flickers are bridged (--max-gap) and brief visits dropped (--min-seconds).
On the real feeder this vision signal is combined with the load cell: pet at bowl AND bowl weight falling.

Example:
  python eating_intervals.py --csv results/cica1.csv --roi 0.55,0.55,1,0.95 --truth "0-44"
"""
import argparse
import csv
import statistics


def load(path):
    rows = list(csv.DictReader(open(path)))
    if not rows or "x1" not in rows[0]:
        raise SystemExit("CSV has no box columns. Re-run benchmark_yolox.py (new version) to create them.")
    return rows


def touches(box, roi):
    return not (box[2] < roi[0] or box[0] > roi[2] or box[3] < roi[1] or box[1] > roi[3])


def intervals_from_flags(times, flags, dt, max_gap, min_seconds):
    runs = []
    for t, f in zip(times, flags):
        if not f:
            continue
        if runs and t - runs[-1][1] <= max_gap + dt * 1.01:
            runs[-1][1] = t
        else:
            runs.append([t, t])
    return [(a, b + dt) for a, b in runs if (b + dt - a) >= min_seconds]


def parse_truth(text):
    out = []
    for part in text.split(","):
        a, b = part.split("-")
        out.append((float(a), float(b)))
    return out


def inside(t, ivs):
    return any(a <= t < b for a, b in ivs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--roi", required=True, help="bowl region, normalised x1,y1,x2,y2 (0-1)")
    ap.add_argument("--margin", type=float, default=0.05, help="extra margin around the ROI (fraction of frame)")
    ap.add_argument("--min-seconds", type=float, default=3.0, help="drop visits shorter than this")
    ap.add_argument("--max-gap", type=float, default=1.5, help="bridge detection gaps up to this long")
    ap.add_argument("--truth", help='your notes as seconds, e.g. "0-30,35-44"')
    a = ap.parse_args()

    roi = [float(v) for v in a.roi.split(",")]
    roi = [max(0, roi[0] - a.margin), max(0, roi[1] - a.margin), min(1, roi[2] + a.margin), min(1, roi[3] + a.margin)]

    rows = load(a.csv)
    times = [float(r["video_time_s"]) for r in rows]
    dt = statistics.median(b - c for b, c in zip(times[1:], times[:-1])) if len(times) > 1 else 0.1
    flags = []
    for r in rows:
        if r["x1"] == "":
            flags.append(False)
            continue
        fw, fh = float(r["frame_w"]), float(r["frame_h"])
        box = (float(r["x1"]) / fw, float(r["y1"]) / fh, float(r["x2"]) / fw, float(r["y2"]) / fh)
        flags.append(touches(box, roi))

    ivs = intervals_from_flags(times, flags, dt, a.max_gap, a.min_seconds)
    near = sum(flags)
    print(f"frames: {len(rows)}   pet near bowl in {near} ({100 * near / len(rows):.0f}%)   sample step {dt:.2f}s")
    print(f"settings: margin {a.margin}  max-gap {a.max_gap}s  min-seconds {a.min_seconds}s")
    print(f"eating intervals found: {len(ivs)}")
    for s, e in ivs:
        print(f"  {s:6.1f}s -> {e:6.1f}s   ({e - s:.1f}s)")

    if a.truth:
        truth = parse_truth(a.truth)
        tp = fp = fn = tn = 0
        for t in times:
            p, g = inside(t, ivs), inside(t, truth)
            tp += p and g
            fp += p and not g
            fn += (not p) and g
            tn += (not p) and not g
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        print(f"\nscored against your notes ({a.truth}) on {len(times)} sampled frames:")
        print(f"  precision {prec:.2f}   recall {rec:.2f}   F1 {f1:.2f}   (TP {tp}, FP {fp}, FN {fn}, TN {tn})")
        print("  precision low = it says 'eating' when she isn't; recall low = it misses real eating")


if __name__ == "__main__":
    main()
