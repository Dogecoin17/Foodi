"""Foodi CCM backend. Run: uvicorn app.main:app --reload  (from the ccm/ folder)."""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from . import protocol as P
from .analytics import clamp_portion, daily_limit_ok, detect_anomalies
from .config import settings
from .feeder_link import FeederLink, make_feeder
from .mcu_bridge import NullMcuBridge, make_mcu_bridge
from .video import VideoPipeline


def _on_local_network() -> bool:
    """True when the CCM has a non-loopback IPv4 (drives the Wi-Fi status LED)."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))  # no traffic is actually sent
            return not s.getsockname()[0].startswith("127.")
    except OSError:
        return False


async def _mcu_task() -> None:
    """Feed the MCU watchdog/status LEDs and poll temperature (NullMcuBridge = no-op)."""
    tick = 0
    while True:
        await asyncio.sleep(2)
        tick += 1
        feeder_ok = bool(state.feeder and state.feeder.connected)
        await state.mcu.set_conn_leds(feeder_ok, _on_local_network())
        if tick % 3 == 0:
            temp = await state.mcu.temperature()
            fan = await state.mcu.fan_on()
            if temp is not None or fan is not None:
                state.system = {"temp_c": temp, "fan_on": fan}
                await state.hub.broadcast({"type": "system", **state.system})


class Hub:
    """Fan-out of live events to connected WebSocket clients."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def broadcast(self, data: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(data)
            except Exception:
                self.clients.discard(ws)


class State:
    feeder: FeederLink | None = None
    hub = Hub()
    latest: dict = {"weight_g": 0, "food_level_pct": None, "state": "IDLE", "ts": None}
    system: dict = {"temp_c": None, "fan_on": None}  # CCM hardware, via the MCU bridge
    mcu: NullMcuBridge | None = None
    video: VideoPipeline | None = None
    pending_manual: set[int] = set()
    next_cmd_id: int = int(time.time()) & 0x3FFFFFFF
    low_food_alerted: bool = False


state = State()


class ScheduleEntry(BaseModel):
    minute_of_day: int = Field(ge=0, lt=1440)
    grams: int = Field(gt=0, le=1000)
    days_mask: int = Field(default=127, ge=1, le=127)


class FeedRequest(BaseModel):
    grams: int = Field(gt=0, le=1000)


class PetIn(BaseModel):
    name: str
    species: str | None = None
    weight_kg: float | None = None
    daily_grams: int | None = None


async def on_feeder_message(msg: P.Message) -> None:
    if msg.type == P.MsgType.EVT_TELEMETRY:
        p = msg.payload
        state.latest = {
            "weight_g": p["weight_g"],
            "food_level_pct": p["food_level_pct"],
            "state": p["state"].name,
            "ts": time.time(),
        }
        db.add_reading(p["weight_g"], p["food_level_pct"])
        if p["state"] == P.FeederState.LOW_FOOD and not state.low_food_alerted:
            state.low_food_alerted = True
            db.add_alert("warning", "Food hopper is running low.")
            await state.hub.broadcast(
                {
                    "type": "alert",
                    "level": "warning",
                    "message": "Food hopper is running low.",
                }
            )
        elif p["state"] != P.FeederState.LOW_FOOD:
            state.low_food_alerted = False
        await state.hub.broadcast({"type": "telemetry", **state.latest})
    elif msg.type == P.MsgType.EVT_DISPENSED:
        p = msg.payload
        source = "manual" if p["cmd_id"] in state.pending_manual else "schedule"
        state.pending_manual.discard(p["cmd_id"])
        db.add_feed_event(p["cmd_id"], p["target_g"], p["actual_g"], source)
        await state.hub.broadcast({"type": "feed_event", "source": source, **p})
    elif msg.type == P.MsgType.EVT_NACK:
        text = f"Feeder rejected a command: {msg.payload['error'].name}"
        db.add_alert("error", text)
        await state.hub.broadcast({"type": "alert", "level": "error", "message": text})


def _schedule_tuples() -> list[tuple[int, int, int]]:
    return [
        (r["minute_of_day"], r["grams"], r["days_mask"])
        for r in db.rows("SELECT * FROM schedule ORDER BY minute_of_day")
    ]


def _parse_roi(raw: str) -> tuple[int, int, int, int] | None:
    try:
        parts = [int(v) for v in raw.split(",")]
        return tuple(parts) if len(parts) == 4 else None
    except ValueError:
        return None


def _on_scale_weight(loop: asyncio.AbstractEventLoop, grams: int) -> None:
    """Called from the video thread with a new scale reading; show it like telemetry."""
    state.latest["weight_g"] = grams
    db.add_reading(grams, state.latest.get("food_level_pct") or 0)

    async def _bcast():
        await state.hub.broadcast({"type": "telemetry", **state.latest})

    asyncio.run_coroutine_threadsafe(_bcast(), loop)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    loop = asyncio.get_running_loop()
    state.mcu = make_mcu_bridge(settings.mcu_mode)
    wifi_creds = (settings.wifi_ssid, settings.wifi_password) if settings.wifi_ssid else None
    state.feeder = make_feeder(settings.feeder_mode, settings.ble_address, wifi_creds)
    state.feeder.subscribe(on_feeder_message)
    await state.feeder.start()
    await state.feeder.set_schedule(_schedule_tuples())
    mcu_task = asyncio.create_task(_mcu_task())
    if settings.video_url:
        model = settings.video_model if Path(settings.video_model).is_file() else ""
        state.video = VideoPipeline(
            settings.video_url,
            model,
            weight_provider=lambda: state.latest.get("weight_g"),
            scale_roi=_parse_roi(settings.scale_roi),
            scale_callback=lambda g: _on_scale_weight(loop, g),
            detector_threads=settings.video_threads,
        )
        state.video.start()
    yield
    mcu_task.cancel()
    if state.video:
        state.video.stop()
    await state.feeder.stop()


app = FastAPI(title="Foodi CCM", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/status")
def status():
    video_mode = (
        "live"
        if state.video
        else ("clip" if Path(settings.video_clip).is_file() else "none")
    )
    out = {
        "connected": bool(state.feeder and state.feeder.connected),
        "mode": settings.feeder_mode,
        "video": video_mode,
        "eating": bool(state.video and state.video.eating),
        **state.system,
        **state.latest,
    }
    if state.video and state.video.detections_done:
        out["video_stats"] = {
            "detections": state.video.detections_done,
            "avg_infer_ms": round(state.video.avg_infer_ms or 0, 1),
            "detect_fps": round(state.video.detect_fps or 0, 1),
        }
    return out


@app.get("/api/pets")
def list_pets():
    return db.rows("SELECT * FROM pets ORDER BY id")


@app.post("/api/pets", status_code=201)
def add_pet(pet: PetIn):
    pet_id = db.execute(
        "INSERT INTO pets(name, species, weight_kg, daily_grams) VALUES(?,?,?,?)",
        (pet.name, pet.species, pet.weight_kg, pet.daily_grams),
    )
    return {"id": pet_id, **pet.model_dump()}


@app.get("/api/schedule")
def get_schedule():
    return db.rows(
        "SELECT minute_of_day, grams, days_mask FROM schedule ORDER BY minute_of_day"
    )


@app.put("/api/schedule")
async def put_schedule(entries: list[ScheduleEntry]):
    cleaned = [
        {**e.model_dump(), "grams": clamp_portion(e.grams, settings.max_portion_g)}
        for e in entries
    ]
    db.replace_schedule(cleaned)
    await state.feeder.set_schedule(_schedule_tuples())
    return cleaned


@app.post("/api/feed")
async def feed(req: FeedRequest):
    grams = clamp_portion(req.grams, settings.max_portion_g)
    if not daily_limit_ok(db.today_dispensed(), grams, settings.daily_max_g):
        raise HTTPException(409, "Daily maximum reached")
    if not (state.feeder and state.feeder.connected):
        raise HTTPException(503, "Feeder not connected")
    state.next_cmd_id += 1
    cmd_id = state.next_cmd_id
    state.pending_manual.add(cmd_id)
    await state.feeder.dispense(cmd_id, grams)
    return {"cmd_id": cmd_id, "grams": grams}


@app.get("/api/events")
def events(limit: int = 50):
    return db.rows("SELECT * FROM feed_events ORDER BY ts DESC LIMIT ?", (limit,))


@app.get("/api/alerts")
def alerts(limit: int = 50):
    return db.rows("SELECT * FROM alerts ORDER BY ts DESC LIMIT ?", (limit,))


@app.get("/api/insights")
def insights():
    return {"anomalies": detect_anomalies(db.daily_dispensed())}


@app.get("/api/history/daily")
def history_daily(days: int = 30):
    days = max(1, min(days, 90))
    return [{"date": d, "grams": g} for d, g in db.daily_history(days)]


async def _mjpeg_stream():
    while True:
        jpeg = state.video.latest_jpeg() if state.video else None
        if jpeg:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
        await asyncio.sleep(0.1)  # ~10 fps to the browser


@app.get("/api/video")
def video():
    """Live MJPEG from the feeder camera (phone in the prototype) with the AI
    overlay, or the pre-recorded clip when no live source is configured."""
    if state.video:
        return StreamingResponse(
            _mjpeg_stream(), media_type="multipart/x-mixed-replace; boundary=frame"
        )
    clip = Path(settings.video_clip)
    if clip.is_file():
        return FileResponse(clip, media_type="video/mp4")
    raise HTTPException(404, "No video configured (set FOODI_VIDEO_URL or FOODI_VIDEO)")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    state.hub.clients.add(ws)
    try:
        await ws.send_json({"type": "telemetry", **state.latest})
        while True:
            await ws.receive_text()  # keep-alive; clients send nothing meaningful
    except WebSocketDisconnect:
        pass
    finally:
        state.hub.clients.discard(ws)


WEB_DIR = Path(__file__).resolve().parents[2] / "web"
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
