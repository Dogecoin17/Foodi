# Foodi - measured resource usage (UNO Q feasibility)

Measured 2026-10-29 17:45 on the development laptop, backend pinned to **1 core(s)** of 32 for 46 s (one modern laptop core is ~3-5x faster than a UNO Q Cortex-A53 core, so this is a conservative stand-in).

## Live measurement (FastAPI + video pipeline + YOLOX-nano)

| Metric | Measured | UNO Q budget | Verdict |
|---|---|---|---|
| Peak memory (RSS) | 190 MB | 2 GB total RAM | OK (<50%) |
| CPU use | 25% of one core | 4x Cortex-A53 @ 2.0 GHz | OK |
| AI detection rate | 557 detections, 12.0 /s | product needs 1-2 /s | OK |
| Avg inference time | 15.5 ms | - | OK |

Video source: ../ai/clips/cica1.mp4

## Offline benchmark (ai/results.csv, --threads 4 to mimic the UNO Q)

| Metric | Value |
|---|---|
| Frames analyzed | 1375 |
| Mean inference | 11.1 ms (max 27.7 ms) |
| Pet found | 99% of frames |

## Notes

- The UNO Q runs the same CPython + onnxruntime + OpenCV stack on aarch64 Debian; all dependencies ship aarch64 wheels.
- The STM32 MCU part (fans, LEDs) is plain Arduino and does not touch this budget.
- Final validation on the real board remains part of the roadmap.
