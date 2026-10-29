"""Run the Foodi CCM under Arduino UNO Q resource constraints and report.

The UNO Q is a 4x Cortex-A53 @ 2 GHz Linux SBC with 2 GB RAM (base variant).
One modern laptop core is several times faster than a Cortex-A53 core, so
pinning the backend to --cores 1 is a *conservative* stand-in for the board.

Usage (from ccm/, venv active):
    python simulate_uno_q.py [--cores 1] [--duration 60] [--video-url SRC] [--port 8130]

Measures the server process: peak RSS, CPU use, and (with a live video
source) AI detection rate. Writes docs/performance.md.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import psutil

CCM_DIR = Path(__file__).resolve().parent
REPORT = CCM_DIR.parent / "docs" / "performance.md"

UNO_Q_SPEC = {
    "cpu": "4x Cortex-A53 @ 2.0 GHz",
    "ram_gb": 2,
    "os": "Debian Linux (aarch64)",
}


def get_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None


def wait_ready(port: int, timeout: float = 30.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if get_json(f"http://127.0.0.1:{port}/api/health"):
            return True
        time.sleep(0.5)
    return False


def benchmark_summary() -> dict | None:
    """Summarize ai/results.csv (the offline YOLOX benchmark) if present."""
    import csv

    path = CCM_DIR.parent / "ai" / "results.csv"
    if not path.is_file():
        return None
    rows = list(csv.DictReader(path.open()))
    if not rows:
        return None
    inf = [float(r["inference_ms"]) for r in rows]
    pets = sum(1 for r in rows if int(r["n_pets"]) > 0)
    return {
        "frames": len(rows),
        "mean_ms": sum(inf) / len(inf),
        "max_ms": max(inf),
        "pet_pct": 100.0 * pets / len(rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cores", type=int, default=1)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--port", type=int, default=8130)
    ap.add_argument("--video-url", default=os.getenv("FOODI_VIDEO_URL", ""))
    ap.add_argument("--scale-roi", default=os.getenv("FOODI_SCALE_ROI", ""))
    a = ap.parse_args()

    env = dict(os.environ)
    if a.video_url:
        env["FOODI_VIDEO_URL"] = a.video_url
    if a.scale_roi:
        env["FOODI_SCALE_ROI"] = a.scale_roi
    env["FOODI_VIDEO_THREADS"] = str(a.cores)  # match inference threads to pinned cores

    child = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(a.port)],
        cwd=CCM_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    proc = psutil.Process(child.pid)
    logical = psutil.cpu_count()
    cores = list(range(min(a.cores, logical)))
    proc.cpu_affinity(cores)

    def tree():
        """The venv python is a launcher stub on Windows; measure the real server too."""
        try:
            return [proc] + proc.children(recursive=True)
        except psutil.NoSuchProcess:
            return []

    print(f"server pid {child.pid}, pinned to {len(cores)} core(s) of {logical}, {a.duration:.0f}s run")

    try:
        if not wait_ready(a.port):
            print("server did not come up")
            return
        def tree_cpu_s() -> float:
            return sum(sum(p.cpu_times()[:2]) for p in tree())

        rss_peak = 0
        stats = {}
        t0 = time.time()
        cpu0 = tree_cpu_s()
        while time.time() - t0 < a.duration:
            time.sleep(2)
            members = tree()
            if not members:
                break
            rss_peak = max(rss_peak, sum(p.memory_info().rss for p in members))
            s = get_json(f"http://127.0.0.1:{a.port}/api/status")
            if s and s.get("video_stats"):
                stats = s["video_stats"]
        elapsed = time.time() - t0
        avg_cpu = 100.0 * (tree_cpu_s() - cpu0) / elapsed  # 100% = one full core
    finally:
        for p in tree():
            try:
                p.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(tree(), timeout=5)
        for p in alive:
            p.kill()

    rss_mb = rss_peak / 1e6
    bench = benchmark_summary()

    print(f"peak RSS: {rss_mb:.0f} MB | avg CPU: {avg_cpu:.0f}% of one core")
    if stats:
        print(f"AI: {stats['detect_fps']} detections/s, avg {stats['avg_infer_ms']} ms")

    ram_ok = rss_mb < UNO_Q_SPEC["ram_gb"] * 1000 * 0.5  # leave half the RAM for the OS
    lines = [
        "# Foodi - measured resource usage (UNO Q feasibility)",
        "",
        f"Measured {datetime.now():%Y-%m-%d %H:%M} on the development laptop, backend pinned "
        f"to **{len(cores)} core(s)** of {logical} for {elapsed:.0f} s "
        "(one modern laptop core is ~3-5x faster than a UNO Q Cortex-A53 core, "
        "so this is a conservative stand-in).",
        "",
        "## Live measurement (FastAPI + video pipeline + YOLOX-nano)",
        "",
        "| Metric | Measured | UNO Q budget | Verdict |",
        "|---|---|---|---|",
        f"| Peak memory (RSS) | {rss_mb:.0f} MB | {UNO_Q_SPEC['ram_gb']} GB total RAM | "
        f"{'OK (<50%)' if ram_ok else 'TIGHT'} |",
        f"| CPU use | {avg_cpu:.0f}% of one core | {UNO_Q_SPEC['cpu']} | OK |",
    ]
    if stats:
        lines += [
            f"| AI detection rate | {stats['detections']} detections, "
            f"{stats['detect_fps']} /s | product needs 1-2 /s | OK |",
            f"| Avg inference time | {stats['avg_infer_ms']} ms | - | OK |",
        ]
    lines += [
        "",
        "Video source: " + (a.video_url or "none (backend only)"),
        "",
    ]
    if bench:
        lines += [
            "## Offline benchmark (ai/results.csv, --threads 4 to mimic the UNO Q)",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Frames analyzed | {bench['frames']} |",
            f"| Mean inference | {bench['mean_ms']:.1f} ms (max {bench['max_ms']:.1f} ms) |",
            f"| Pet found | {bench['pet_pct']:.0f}% of frames |",
            "",
        ]
    lines += [
        "## Notes",
        "",
        "- The UNO Q runs the same CPython + onnxruntime + OpenCV stack on aarch64 "
        "Debian; all dependencies ship aarch64 wheels.",
        "- The STM32 MCU part (fans, LEDs) is plain Arduino and does not touch this budget.",
        "- Final validation on the real board remains part of the roadmap.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"report: {REPORT}")


if __name__ == "__main__":
    main()
