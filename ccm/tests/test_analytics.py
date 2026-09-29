from app.analytics import clamp_portion, daily_limit_ok, detect_anomalies


def test_clamp():
    assert clamp_portion(500, 200) == 200
    assert clamp_portion(-5, 200) == 0
    assert clamp_portion(50, 200) == 50


def test_daily_limit():
    assert daily_limit_ok(500, 100, 600)
    assert not daily_limit_ok(500, 101, 600)


def test_no_anomaly_on_normal_days():
    assert detect_anomalies([200, 205, 198, 202, 201, 199, 203]) == []


def test_low_consumption_flagged():
    res = detect_anomalies([200, 205, 198, 202, 201, 199, 203, 120])
    assert res and res[0]["kind"] == "consumption_low"
    assert "vet" in res[0]["message"]


def test_needs_enough_history():
    assert detect_anomalies([200, 100]) == []
