"""Foodi CCM backend. Run: uvicorn app.main:app --reload  (from the ccm/ folder)."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from . import protocol as P
from .analytics import clamp_portion, daily_limit_ok, detect_anomalies
from .config import settings
from .feeder_link import FeederLink, make_feeder


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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    state.feeder = make_feeder(settings.feeder_mode, settings.ble_address)
    state.feeder.subscribe(on_feeder_message)
    await state.feeder.start()
    await state.feeder.set_schedule(_schedule_tuples())
    yield
    await state.feeder.stop()


app = FastAPI(title="Foodi CCM", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/status")
def status():
    return {
        "connected": bool(state.feeder and state.feeder.connected),
        "mode": settings.feeder_mode,
        **state.latest,
    }


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


@app.get("/api/video")
def video():
    raise HTTPException(501, "Video pipeline arrives in Phase 5")


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
