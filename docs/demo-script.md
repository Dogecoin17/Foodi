# Foodi demo script (3–5 min, fully offline)

## Live camera via phone (video-prototype setup)
1. Install an IP webcam app on a phone (Android: **IP Webcam**; iPhone: **EpocCam**).
2. Put the phone and the CCM on the same Wi-Fi; start the stream
   (IP Webcam: "Start server", note the URL, e.g. `http://192.168.1.50:8080/video`).
3. Start the backend with the live source:
   `FOODI_VIDEO_URL=http://<phone-ip>:8080/video python -m uvicorn app.main:app`
4. The dashboard's Live view now shows the phone stream with the AI overlay
   (green box = pet detected, red + "EATING" = eating detected).
   If the phone drops, the backend reconnects automatically.
   Rehearse without a phone: `FOODI_VIDEO_URL=../ai/clips/cica1.mp4`.

## Reading the kitchen scale through the camera
The backend decodes the scale's 7-segment LCD directly from the video -
no wiring to the scale at all.

1. Put the scale under/next to the bowl with its display facing the phone camera,
   roughly frontal. Fix the phone; the camera must not move afterwards.
2. Grab a still frame: open `http://<phone-ip>:8080/photo.jpg` in a browser and
   save it. In any image viewer (Paint works), note the pixel coordinates of the
   display's top-left and bottom-right corners.
3. Start the backend with the region:
   `FOODI_VIDEO_URL=http://<phone-ip>:8080/video FOODI_SCALE_ROI=x1,y1,x2,y2 python -m uvicorn app.main:app`
4. The dashboard bowl weight now follows the real scale. The overlay draws a
   yellow box around the display with the decoded value; when the pet blocks
   the display, the last reading is held on purpose.

Notes: LCD glare kills the reading - angle the phone so no lamp reflects on the
display. Readings are median-filtered over 5 frames; one misread frame never
reaches the dashboard.

Rehearse twice. Everything runs on the laptop (or the UNO Q); no internet needed.

## Setup before the judges arrive

### On the UNO Q (the real CCM)
1. Plug the UNO Q into a laptop via USB-C and open Arduino App Lab.
2. Follow first-time setup: set the Linux password, then enter the local Wi-Fi
   credentials when App Lab asks (Settings -> Advanced Network Configuration also
   works in SBC mode). From now on the board is reachable as `http://<uno-q-ip>`.
3. Copy the repo to the board (git clone or scp), then on the board:
   `cd ccm && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
4. Seed and start: `.venv/bin/python -m app.seed_demo --force` then
   `.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0`

### On a laptop (fallback, same flow)
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
