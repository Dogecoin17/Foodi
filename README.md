# Foodi

Foodi is an automated pet-feeding ecosystem designed to help improve the eating habits and overall well-being of household pets. Powered by the Arduino UNO Q and ESP32-S3 hardware, Foodi combines artificial intelligence, smart hardware, and a user-friendly design to provide intelligent, personalized feeding.

Whether a pet has a gastric condition, needs help managing its weight, or simply requires scheduled meals while its owner is away, Foodi is designed to make feeding more consistent and convenient.

Read **PLAN.md** first – it is the build plan with phases, checklists, and definitions of done.

## How it works

Foodi consists of two main components:

- **Central Computing Module (CCM):** The central hub of the system. It contains an Arduino UNO Q running an AI model that analyzes pets' eating patterns and helps determine optimized feeding schedules and portion recommendations. The CCM also provides health-related insights and suggestions based on the collected data.
- **Feeder:** A peripheral module mounted on a wireless, movable feeder unit. It dispenses food according to the schedule determined by the CCM and includes a camera that sends a live video feed back for monitoring and analysis.

The Feeder and CCM communicate over Bluetooth for fast, reliable data exchange while minimizing packet loss. The CCM also uses Wi‑Fi to send relevant information to a web application, allowing owners to monitor their pets and manage the system remotely.

## Example setup

The CCM is placed in a suitable location indoors and connected to a power supply. A feeder unit is positioned on the floor, connected to a wall outlet, and paired with the CCM. Once connected, the system can manage feeding schedules and collect information about the pet's eating habits.

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
Open http://localhost:8000 – press **Feed now**, edit the schedule, and watch live updates.
In VS Code: *Terminal > Run Task > CCM: run backend* or press F5 ("CCM backend (debug)").
Select the `ccm/.venv` interpreter (Ctrl+Shift+P > Python: Select Interpreter).

## Tests
```
cd ccm && python -m pytest
```

## Real hardware
```
FOODI_FEEDER=ble FOODI_BLE_ADDRESS=<feeder MAC> python -m uvicorn app.main:app
```
(BLE client and firmware are skeletons – see PLAN.md phases 2–3.)

## CCM dimensions

The CCM is designed with a sleek appearance inspired by the Mac Studio. Ventilation openings help maintain continuous airflow and support reliable operation.

- **Height:** 5.0 cm
- **Width:** 12.7 cm
- **Depth:** 12.7 cm
- **Weight:** To be determined after the first prototype is printed

## Status of this scaffold
| Part | State |
|---|---|
| BLE protocol encode/decode + tests | working, unit-tested |
| Analytics (clamps, anomaly detection) + tests | working, unit-tested |
| FakeFeeder simulator | working (ack, dispense, telemetry, idempotent retry, limits) |
| FastAPI app + web dashboard | written, **not yet run** – first thing to try |
| BleFeeder, feeder firmware, vision, Bridge | skeletons / TODO |
