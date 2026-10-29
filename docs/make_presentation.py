"""Build the Foodi competition deck: python docs/make_presentation.py

Screenshots: drop PNGs into docs/screenshots/ and re-run - they are embedded
automatically. Recognized files:
  dashboard.png   live dashboard (status + feed now)
  chart.png       daily consumption chart with the anomaly
  video.png       live view with the AI overlay
Missing files become labeled placeholder boxes.

Uses python-pptx (pip install python-pptx). Output: docs/Foodi.pptx
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent
SHOTS = ROOT / "screenshots"
OUT = ROOT / "Foodi.pptx"

ACCENT = RGBColor(0xE8, 0x74, 0x3B)
INK = RGBColor(0x1C, 0x1F, 0x24)
MUTED = RGBColor(0x6B, 0x72, 0x80)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
SW, SH = prs.slide_width, prs.slide_height


def slide():
    return prs.slides.add_slide(BLANK)


def text(s, x, y, w, h, runs, size=20, color=INK, bold=False, align=None):
    """runs: str or list of paragraphs (each a str)."""
    box = s.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    paras = [runs] if isinstance(runs, str) else runs
    for i, line in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if align is not None:
            p.alignment = align
        if line.startswith("- "):
            p.text = "•  " + line[2:]
        else:
            p.text = line
        p.space_after = Pt(8)
        for r in p.runs:
            r.font.size = Pt(size)
            r.font.color.rgb = color
            r.font.bold = bold
    return box


def title(s, text_, sub=None):
    bar = s.shapes.add_shape(1, 0, 0, Inches(0.25), SH)  # accent bar
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    text(s, Inches(0.6), Inches(0.35), SW - Inches(1.2), Inches(0.9), text_, size=34, bold=True)
    if sub:
        text(s, Inches(0.6), Inches(1.15), SW - Inches(1.2), Inches(0.5), sub, size=16, color=MUTED)


def picture_or_placeholder(s, name, x, y, w, h, label):
    f = SHOTS / name
    if f.is_file():
        s.shapes.add_picture(str(f), x, y, width=w, height=h)
    else:
        ph = s.shapes.add_shape(1, x, y, w, h)
        ph.fill.solid()
        ph.fill.fore_color.rgb = RGBColor(0xEF, 0xEF, 0xEF)
        ph.line.color.rgb = MUTED
        tf = ph.text_frame
        tf.word_wrap = True
        tf.text = f"[ screenshot: {label} ]\ndrop {name} into docs/screenshots/ and re-run"
        for p in tf.paragraphs:
            for r in p.runs:
                r.font.size = Pt(14)
                r.font.color.rgb = MUTED


# 1 - title --------------------------------------------------------------------
s = slide()
band = s.shapes.add_shape(1, 0, Inches(2.6), SW, Inches(2.3))
band.fill.solid()
band.fill.fore_color.rgb = ACCENT
band.line.fill.background()
text(s, Inches(1), Inches(2.9), SW - Inches(2), Inches(1), "Foodi", size=60, bold=True, color=RGBColor(255, 255, 255))
text(s, Inches(1), Inches(3.9), SW - Inches(2), Inches(0.8),
     "Automated modular pet feeding with local AI diet insights", size=24, color=RGBColor(255, 255, 255))
text(s, Inches(1), Inches(6.6), SW - Inches(2), Inches(0.5),
     "Robotics competition - built on Arduino UNO Q + ESP32-S3 - team: [names]", size=14, color=MUTED)

# 2 - problem -------------------------------------------------------------------
s = slide()
title(s, "The problem", "Why pets need Foodi")
text(s, Inches(0.8), Inches(1.9), Inches(6), Inches(4.8), [
    "- Inconsistent portions and irregular feeding times lead to obesity and digestive issues",
    "- Owners are away at work or on trips - feeding still has to happen, on time",
    "- Early appetite changes are the first symptom of many illnesses, and the easiest to miss",
    "- Existing smart feeders dispense food; none of them watch what the pet actually eats",
], size=20)
text(s, Inches(7.3), Inches(1.9), Inches(5.4), Inches(4.8), [
    "Our answer",
    "- Automated, scheduled, portion-accurate feeding",
    "- Camera + load cell observe every meal",
    "- Local AI learns the eating pattern and flags changes early",
    "- Fully offline: no cloud, no subscription, no privacy leak",
], size=20, color=ACCENT)

# 3 - system --------------------------------------------------------------------
s = slide()
title(s, "System overview", "Two modules, one ecosystem")
text(s, Inches(0.8), Inches(1.8), Inches(5.6), Inches(3.2), [
    "CCM - Central Computing Module",
    "- Arduino UNO Q (Linux): FastAPI backend, SQLite, scheduler, AI inference",
    "- Wi-Fi + Bluetooth radios, battery management, wall power",
], size=18)
text(s, Inches(0.8), Inches(4.6), Inches(5.6), Inches(2.2), [
    "Feeder module",
    "- ESP32-S3: auger motor, HX711 load cell, camera",
    "- Own battery + BMS, runs its schedule autonomously",
], size=18)
text(s, Inches(6.9), Inches(1.8), Inches(5.8), Inches(5), [
    "Data flow",
    "- Feeder -> CCM (BLE): weight, food level, meal events",
    "- CCM -> Feeder (BLE): dispense, schedule sync, time sync",
    "- Feeder -> CCM (Wi-Fi): camera stream",
    "- CCM -> owner (Wi-Fi, web app): dashboard, live view, insights",
    "",
    "Setup: owner joins the CCM to the home Wi-Fi once via Arduino App Lab,",
    "pairs the feeder over Bluetooth, and the feeder joins Wi-Fi for video.",
], size=18)

# 4 - firmware ------------------------------------------------------------------
s = slide()
title(s, "Feeder firmware", "ESP32-S3, implements the Foodi BLE protocol v1")
text(s, Inches(0.8), Inches(1.9), Inches(6), Inches(4.8), [
    "- Closed-loop dispensing: auger runs fast, then slows near the target; load cell decides when to stop",
    "- Jam / empty-hopper guard: 20 s timeout, motor off on any fault",
    "- Idempotent commands: a retried command id can never dispense twice",
    "- Schedule stored in flash: the feeder feeds on time even with Bluetooth down",
    "- Missed meals are reported to the CCM on reconnect",
], size=18)
text(s, Inches(7.3), Inches(1.9), Inches(5.4), Inches(4.8), [
    "Status",
    "- Full firmware builds clean in PlatformIO: 23% flash, 10% RAM",
    "- Protocol shared byte-for-byte with the CCM (unit-tested both sides)",
    "- Hard 200 g portion limit enforced on the feeder itself",
    "- Next: flash hardware and run the 24 h soak test",
], size=18, color=ACCENT)

# 5 - AI ------------------------------------------------------------------------
s = slide()
title(s, "Local AI", "From video + weight to a healthy diet")
text(s, Inches(0.8), Inches(1.9), Inches(6), Inches(4.8), [
    "- YOLOX-nano detector finds the pet at the bowl (cat/dog, COCO pretrained)",
    "- Eating = pet in the bowl region for >= 5 s AND bowl weight decreasing",
    "- Consumed grams per meal, not just dispensed grams",
    "- Rolling-baseline anomaly detection (z-score) on daily intake",
    "- Insights are observations, never diagnoses",
], size=18)
text(s, Inches(7.3), Inches(1.9), Inches(5.4), Inches(4.8), [
    "Measured on real footage",
    "- 1,375 frames analyzed, pet found in 99%",
    "- 11 ms average inference (max 28 ms) - real-time even on the UNO Q",
    "- Demo insight: intake 45% below the 14-day average for 2 days -> alert",
    "",
    "Fits the UNO Q (measured, pinned to 1 core):",
    "- 190 MB RAM of 2 GB, 25% CPU, 12 detections/s (need 1-2)",
], size=18, color=ACCENT)

# 6 - demo ----------------------------------------------------------------------
s = slide()
title(s, "Live demo", "Dashboard on the owner's phone")
picture_or_placeholder(s, "dashboard.png", Inches(0.8), Inches(1.8), Inches(3.8), Inches(4.6), "dashboard")
picture_or_placeholder(s, "video.png", Inches(4.85), Inches(1.8), Inches(3.8), Inches(4.6), "live view with AI overlay")
picture_or_placeholder(s, "chart.png", Inches(8.9), Inches(1.8), Inches(3.8), Inches(4.6), "daily consumption chart")
text(s, Inches(0.8), Inches(6.6), SW - Inches(1.6), Inches(0.6),
     "Feed now - schedule - live telemetry over WebSocket - anomaly insight - pre-recorded AI video fallback",
     size=14, color=MUTED)

# 7 - safety --------------------------------------------------------------------
s = slide()
title(s, "Safety & reliability", "A feeding robot must never harm the pet")
text(s, Inches(0.8), Inches(1.9), Inches(6), Inches(4.8), [
    "- Portion clamped twice: CCM limit AND an independent 200 g hard limit in firmware",
    "- Daily maximum enforced by the backend",
    "- Motor is off at boot and after any fault",
    "- Jam / empty hopper -> safe stop + alert",
    "- Idempotent command ids: no double feeding, ever",
], size=18)
text(s, Inches(7.3), Inches(1.9), Inches(5.4), Inches(4.8), [
    "- Feeder is autonomous: feeds on schedule without Bluetooth or Wi-Fi",
    "- Reconnect with backoff; time + schedule re-sync on every reconnect",
    "- Low-food alert before the hopper runs dry",
    "- 17 automated tests cover protocol, clamps, analytics, and the API",
], size=18)

# 8 - roadmap -------------------------------------------------------------------
s = slide()
title(s, "Roadmap", "What the next weeks add")
text(s, Inches(0.8), Inches(1.9), Inches(11.8), Inches(4.8), [
    "- Flash the firmware on the real ESP32-S3 + HX711 and pass the 24 h soak test",
    "- Live MJPEG camera stream from the feeder to the dashboard (endpoint ready, clip fallback today)",
    "- Per-pet recognition for multi-pet homes (50-100 photos per pet)",
    "- Portion recommendations tuned with a vet, bounded by owner-set limits",
    "- Remote access over HTTPS (Cloudflare Tunnel / Tailscale) with a login",
    "- 48 h unattended run as the final reliability gate",
], size=20)

# 9 - closing -------------------------------------------------------------------
s = slide()
band = s.shapes.add_shape(1, 0, Inches(3), SW, Inches(1.6))
band.fill.solid()
band.fill.fore_color.rgb = ACCENT
band.line.fill.background()
text(s, Inches(1), Inches(3.25), SW - Inches(2), Inches(1),
     "Foodi - the feeder that watches what your pet actually eats.",
     size=28, bold=True, color=RGBColor(255, 255, 255))
text(s, Inches(1), Inches(5), SW - Inches(2), Inches(0.6),
     "Thank you - questions welcome", size=18, color=MUTED)

prs.save(OUT)
print(f"wrote {OUT} ({len(prs.slides._sldIdLst)} slides)")
missing = [n for n in ("dashboard.png", "video.png", "chart.png") if not (SHOTS / n).is_file()]
if missing:
    print("placeholders used for:", ", ".join(missing), "-> drop files into docs/screenshots/ and re-run")
