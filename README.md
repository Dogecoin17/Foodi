# Foodi – digital system

Automated pet feeder: **CCM** (Arduino UNO Q, runs AI + backend) and **Feeder** (ESP32-S3, dispenses food + camera).
Read **PLAN.md** first – it is the build plan with phases, checklists and definitions of done.

## Open in VS Code
```
code foodi.code-workspace
```
Accept the "install recommended extensions" prompt (Python, Ruff, PlatformIO, C/C++).

## Run the backend with the simulated feeder (no hardware needed)
```
cd ccm
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```
Open http://localhost:8000 – press **Feed now**, edit the schedule, watch live updates.
In VS Code: *Terminal > Run Task > CCM: run backend*, or press F5 ("CCM backend (debug)").
Select the `ccm/.venv` interpreter (Ctrl+Shift+P > Python: Select Interpreter).

## Tests
```
cd ccm && python -m pytest
```

## Real hardware
`FOODI_FEEDER=ble FOODI_BLE_ADDRESS=<feeder MAC> python -m uvicorn app.main:app`
(BLE client and firmware are skeletons – see PLAN.md phases 2–3.)

## Status of this scaffold
| Part | State |
|---|---|
| BLE protocol encode/decode + tests | working, unit-tested |
| Analytics (clamps, anomaly detection) + tests | working, unit-tested |
| FakeFeeder simulator | working (ack, dispense, telemetry, idempotent retry, limits) |
| FastAPI app + web dashboard | written, **not yet run** – first thing to try |
| BleFeeder, feeder firmware, vision, Bridge | skeletons / TODO |
