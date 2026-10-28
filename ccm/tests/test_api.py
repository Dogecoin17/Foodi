import os
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

os.environ["FOODI_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["FOODI_FEEDER"] = "fake"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_health_and_status():
    with TestClient(app) as c:
        assert c.get("/api/health").json() == {"ok": True}
        assert c.get("/api/status").json()["connected"] is True


def test_schedule_roundtrip_and_clamp():
    with TestClient(app) as c:
        r = c.put("/api/schedule", json=[{"minute_of_day": 480, "grams": 900, "days_mask": 127}])
        assert r.status_code == 200
        assert c.get("/api/schedule").json()[0]["grams"] == 200  # clamped to max portion


def test_feed_now_is_logged():
    import time

    with TestClient(app) as c:
        r = c.post("/api/feed", json={"grams": 30})
        assert r.status_code == 200
        time.sleep(2.5)
        events = c.get("/api/events").json()
        assert events and events[0]["source"] == "manual"


def test_pets():
    with TestClient(app) as c:
        assert c.post("/api/pets", json={"name": "Milo", "species": "cat"}).status_code == 201
        assert c.get("/api/pets").json()[0]["name"] == "Milo"


def test_video_not_ready(tmp_path, monkeypatch):
    import app.main as m

    monkeypatch.setattr(m, "VIDEO_PATH", tmp_path / "missing.mp4")
    with TestClient(app) as c:
        assert c.get("/api/video").status_code == 404


def test_video_serves_clip():
    with TestClient(app) as c:
        r = c.get("/api/video")
        assert r.status_code == 200
        assert r.headers["content-type"] == "video/mp4"


def test_daily_history():
    with TestClient(app) as c:
        r = c.get("/api/history/daily?days=7")
        assert r.status_code == 200
        assert all(set(d) == {"date", "grams"} for d in r.json())
