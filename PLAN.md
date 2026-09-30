# Foodi – Digital System Build Plan

This plan is the canonical delivery roadmap for the Foodi project described in [README.md](README.md). It defines the milestones, interfaces, and proof points for the digital system: feeder firmware, CCM software, AI, web app, and the links between them.

Tick boxes as you go; every phase ends with a **Definition of Done (DoD)** you can demo.

## Project summary
Foodi is an automated pet-feeding ecosystem designed to improve eating habits and overall well-being. It combines AI, smart hardware, and a simple owner workflow to provide consistent and personalized feeding.

The system has two main components:
- **Central Computing Module (CCM):** the hub for scheduling, analytics, and owner-facing controls. It runs the FastAPI backend and simulator and is the home for the AI-driven feeding logic.
- **Feeder:** the autonomous dispensing unit mounted on a feeder. It executes the schedule, tracks bowl weight/food level, and streams camera data when connected.

The system is intentionally designed around a simulator-first workflow so development can continue without physical hardware. The repository contains the FastAPI backend, a fake feeder simulator, starter firmware, and the web app shell.

## Quickstart and current scaffold state
The following setup notes are the baseline for the plan and should be treated as the minimum working path for contributors.

### Open in VS Code
```bash
code foodi.code-workspace
```
Accept the recommended extension prompt for Python, Ruff, PlatformIO, and C/C++.

### Run the backend with the simulated feeder
```bash
cd ccm
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```
Open http://localhost:8000, then press **Feed now**, edit the schedule, and watch live updates.

### Tests
```bash
cd ccm && python -m pytest
```

### Real hardware
```bash
FOODI_FEEDER=ble FOODI_BLE_ADDRESS=<feeder MAC> python -m uvicorn app.main:app
```
The BLE client and firmware are still skeletons; the real hardware path is a later milestone.

### Current scaffold status
| Part | State |
|---|---|
| BLE protocol encode/decode + tests | working, unit-tested |
| Analytics (clamps, anomaly detection) + tests | working, unit-tested |
| FakeFeeder simulator | working (ack, dispense, telemetry, idempotent retry, limits) |
| FastAPI app + web dashboard | written, **not yet run** – first thing to try |
| BleFeeder, feeder firmware, vision, bridge | skeletons / TODO |

## Guiding principles
1. **Simulator first.** The CCM runs against a `FakeFeeder`, so software progress never waits for hardware.
2. **Write the interface before the code.** BLE protocol (`docs/ble-protocol.md`) and REST API (`docs/api.md`) are frozen at v1 in Phase 0.
3. **Feeder is autonomous.** It stores its schedule and keeps feeding if Bluetooth drops. The CCM monitors and syncs.
4. **Idempotent commands.** Every dispense carries a unique `cmd_id`; retries can never double-feed.
5. **Safety clamps everywhere.** Max portion and max daily grams are enforced on the CCM *and* on the feeder. The AI can only suggest within owner-set limits.
6. **Local-first.** Backend and database run on the CCM; the demo must work with no internet.

## Architecture
```
FEEDER (ESP32-S3 + camera)              CCM (Arduino UNO Q)                        OWNER
 motor, load cell, food level  <-BLE->   Linux: FastAPI, SQLite, scheduler, AI  <-HTTPS/WS-> Web app (PWA)
 local schedule, camera        --WiFi->  MCU: real-time I/O (Bridge RPC)
```
| Link | Tech | Carries |
|---|---|---|
| Feeder <-> CCM control | BLE GATT | dispense, tare, schedule sync, status, weight, food level |
| Feeder -> CCM video | Wi-Fi (MJPEG) | camera stream |
| CCM <-> Web app | REST + WebSocket | config, commands, live status, video |
| CCM Linux <-> MCU | Arduino Bridge (RPC) | on-board sensors / actuators |

## Repo layout
```
ccm/      Python backend (FastAPI), simulator, protocol, analytics, vision stubs, tests
feeder/   PlatformIO firmware skeleton (ESP32-S3)
web/      Dashboard (PWA) served by the backend
docs/     BLE protocol, API notes
```

---
## Phase 0 – Setup and decisions (days 1–3)
- [ ] Create git repo from this scaffold; agree branch/PR routine
- [ ] Run the backend simulator on every teammate's laptop (`README.md`)
- [ ] Get the UNO Q running: Arduino App Lab, Python + sketch "hello", one Bridge round trip. **Record** CPU/RAM, Python version, what inference runtimes work
- [ ] Confirm feeder MCU (ESP32-S3 with camera recommended) and PlatformIO toolchain
- [ ] Confirm with hardware team: motor type, load cell + HX711, food-level sensor, power (wall vs battery)
- [ ] Review and freeze BLE spec v1 and REST API v1 with the hardware/firmware people

**DoD:** everyone can run the simulator; UNO Q hello-world works; interfaces frozen.

## Phase 1 – CCM backend core on the simulator (week 1)
- [ ] SQLite schema and data access (`db.py`)
- [ ] Protocol encode/decode with unit tests (`protocol.py`)
- [ ] `FeederLink` interface + `FakeFeeder` (executes schedules, emits telemetry)
- [ ] REST endpoints: status, feed now, schedule CRUD, events, alerts, insights
- [ ] WebSocket live updates
- [ ] Safety clamps (max portion, daily max)

**DoD:** with no hardware, press "Feed now" via API and see the event logged and broadcast.

## Phase 2 – Feeder firmware (weeks 1–2, in parallel)
- [ ] Bring up load cell (HX711): tare, calibrate with a known mass, filter noise
- [ ] Motor control: auger dispense to target grams with closed-loop weight feedback and timeout/jam detection
- [ ] Local schedule storage (NVS) and RTC/time-sync
- [ ] BLE peripheral (NimBLE): command, status, telemetry characteristics per spec
- [ ] Safety: max portion, low-food state, watchdog, safe motor-off on any fault
- [ ] Camera streaming over Wi-Fi (MJPEG) as a separate task

**DoD:** feeder dispenses 30 g +/- 3 g on command from a BLE test app (nRF Connect), and follows a stored schedule with the phone disconnected.

## Phase 3 – BLE integration (week 2–3)
- [ ] `BleFeeder` with `bleak`: connect, subscribe, write, auto-reconnect with backoff
- [ ] Time sync and schedule sync on every (re)connect
- [ ] Command retry with ACK timeout (same `cmd_id`)
- [ ] Soak test: 24 h with random disconnects, no double-feeds, no missed meals

**DoD:** simulator swapped for real feeder with one env var (`FOODI_FEEDER=ble`).

## Phase 4 – Web app MVP (weeks 2–3)
- [ ] Dashboard: connection state, food level, bowl weight, next meal
- [ ] Feed now, schedule editor, feeding history, alerts list
- [ ] PWA manifest so it installs on a phone
- [ ] Simple login (single owner PIN/password) before any remote access
- [ ] Remote access via Cloudflare Tunnel or Tailscale (HTTPS)

**DoD:** owner controls the feeder from a phone on another network.

## Phase 5 – Video pipeline (week 3)
- [ ] Feeder MJPEG stream -> CCM ingest (OpenCV or plain HTTP reader)
- [ ] Re-serve to the web app at `/api/video`
- [ ] Frame-rate and resolution budget: target 640x480 @ 5–10 fps for viewing, 1–2 fps for AI

**DoD:** live view in the web app with < 1 s latency on local Wi-Fi.

## Phase 6 – Vision AI (weeks 3–4)
- [ ] Pretrained nano detector (YOLO nano or MobileNet-SSD, int8 TFLite/ONNX); cat/dog from COCO
- [ ] Benchmark on the UNO Q; choose input size and fps
- [ ] Bowl region-of-interest (ROI) configuration in the web app
- [ ] Eating detection = pet in ROI for N s **and** bowl weight decreasing
- [ ] Optional: per-pet ID classifier for multi-pet homes (50–100 photos per pet)

**DoD:** correct "pet ate X g over Y min" events on recorded test footage.

## Phase 7 – Analytics and insights (weeks 4–5)
- [ ] Replace dispensed-grams with consumed-grams (bowl weight drop) in insights
- [ ] Rolling-baseline anomaly detection (z-score, later Isolation Forest)
- [ ] Portion recommendations: rule-based, bounded by owner/vet limits
- [ ] Insight wording = observations only, never diagnoses
- [ ] Simulated 30-day pet histories for development and demo

**DoD:** injected "pet eats 40% less for 2 days" produces an alert and a suggestion.

## Phase 8 – Hardening (week 5–6)
- [ ] Failure drills: BLE drop, Wi-Fi drop, power cycle CCM, power cycle feeder, empty hopper, jam
- [ ] Startup on boot (systemd service on the UNO Q), log rotation, DB backup
- [ ] Security pass: auth, no default passwords, HTTPS only for remote
- [ ] Load/latency check with 2 phones connected

**DoD:** 48 h unattended run with no intervention.

## Phase 9 – Demo and documentation (final week)
- [ ] Offline demo path: own router/hotspot, pre-recorded video fallback
- [ ] Demo script (3–5 min): setup -> schedule -> feed now -> pet eats -> insight alert
- [ ] Architecture diagram, protocol spec, test results for the judges
- [ ] Rehearse twice, including "what if the Wi-Fi dies"

## Cut line (if time runs short)
**Must have:** Phases 1–4, basic eating detection, one insight.
**Should have:** video streaming, remote access, safety drills.
**Nice to have:** multi-pet ID, Isolation Forest, cloud sync, push notifications.

## Risks
| Risk | Mitigation |
|---|---|
| BLE unreliable / range issues | feeder autonomous; retry with idempotent IDs; Wi-Fi/MQTT fallback for control |
| UNO Q too slow for vision | nano model, int8, 1–2 fps, crop to ROI; move detection to feeder ESP32-S3 as fallback |
| No real pet data | simulator + recorded footage; heuristic eating detection needs no training |
| Venue Wi-Fi unreliable | local-first, own hotspot, recorded video backup |
| Load cell drift/noise | tare before each meal, median filter, temperature-stable mounting |
| Feeder jams | current/timeout detection, alert, safe stop |
| Integration late | fake feeder from day 1; freeze interfaces early |

## Testing strategy
- Unit: protocol round-trips, analytics, clamps (`pytest`)
- API: FastAPI TestClient against `FakeFeeder`
- Hardware-in-loop: nRF Connect scripts for firmware before the CCM ever touches it
- Soak: 24–48 h with random faults
- Vision: recorded clips with hand-labelled "eating" intervals

## Open decisions
- [ ] Feeder power: wall only or battery too?
- [ ] BLE for control (planned) vs Wi-Fi/MQTT (fallback)
- [ ] Which pets for the demo (portion range and hopper size follow from this)
- [ ] Frontend: plain JS (scaffolded) vs React
