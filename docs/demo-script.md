# Foodi demo script (3–5 min, fully offline)

Rehearse twice. Everything runs on the laptop (or the UNO Q); no internet needed.

## Setup before the judges arrive
1. Fresh demo DB with history: `cd ccm && python -m app.seed_demo --force`
2. Start the backend: `python -m uvicorn app.main:app`
3. Open http://localhost:8000, confirm: video clip plays, dashboard shows "feeder connected".

## Script

1. **The problem (30 s).** Pets need consistent portions and schedules; owners can't always
   be there, and early changes in appetite are easy to miss.
2. **The system (30 s).** Show the architecture: feeder (ESP32-S3, load cell, camera) talks
   BLE to the CCM (UNO Q), video over Wi-Fi, web app on the owner's phone. Everything local.
3. **Live view (30 s).** Point at the video card: real recorded footage of a cat at the bowl
   with the AI detection overlay (`ai/results/cica1_roi.mp4`). This is what the owner sees.
4. **Feed now (30 s).** Press *Feed now* with 30 g. Watch bowl weight rise live via WebSocket
   telemetry and the event appear in the feeding history. Mention: the feeder ACKs every
   command, retries are idempotent – it can never double-feed.
5. **Schedule (30 s).** Add a meal for the next minute, watch it fire on its own. Mention:
   the schedule lives *on the feeder*; it keeps feeding even if Bluetooth drops.
6. **The insight (60 s).** Scroll to *Daily consumption*: 28 normal days, then 2 red days
   ~40% lower. Show *Insights*: "Today's amount is about 45% below the recent average…".
   This is the AI value proposition: the system notices appetite changes early, wording is
   observational, never a diagnosis. Mention the YOLO-nano benchmark on the UNO Q
   (`ai/results.csv`).
7. **Safety (30 s).** Try to feed 900 g: the CCM clamps it to the 200 g max portion, and the
   feeder would reject anything above its own hard limit anyway. Low-food and jam alerts
   appear in the alerts list.

## If something breaks
- **Backend dies:** restart it; the DB is on disk, nothing is lost.
- **WebSocket stalls:** refresh the page; state reloads from the REST API.
- **Video missing:** the card hides itself; narrate with the architecture diagram instead.
- **Worst case:** have this repo open plus screenshots of the dashboard in the slide deck.
