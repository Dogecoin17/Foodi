# REST / WebSocket API v1 (served by the CCM)

| Method | Path | Purpose |
|---|---|---|
| GET | /api/health | liveness |
| GET | /api/status | connection, latest weight, food level, state |
| GET / POST | /api/pets | list / add pets |
| GET / PUT | /api/schedule | read / replace schedule (also pushed to feeder) |
| POST | /api/feed | `{grams}` manual dispense (clamped) |
| GET | /api/events?limit=50 | feeding history |
| GET | /api/alerts?limit=50 | alerts |
| GET | /api/insights | anomaly / health observations |
| GET | /api/video | MJPEG stream (Phase 5, currently 501) |
| WS | /ws | live `telemetry`, `feed_event`, `alert` messages |

Schedule entry: `{"minute_of_day": 480, "grams": 40, "days_mask": 127}` (127 = every day).
