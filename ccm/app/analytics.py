"""Safety clamps and simple, explainable health analytics."""
from __future__ import annotations

from statistics import mean, stdev


def clamp_portion(requested_g: int, max_portion_g: int) -> int:
    return max(0, min(int(requested_g), max_portion_g))


def daily_limit_ok(today_total_g: int, requested_g: int, daily_max_g: int) -> bool:
    return today_total_g + requested_g <= daily_max_g


def detect_anomalies(daily_totals: list[float], window: int = 14, z_threshold: float = 2.0) -> list[dict]:
    """Compare the latest day with a rolling baseline. Wording is observational, never a diagnosis."""
    if len(daily_totals) < 5:
        return []
    baseline = daily_totals[-(window + 1):-1]
    latest = daily_totals[-1]
    mu = mean(baseline)
    sd = stdev(baseline) if len(baseline) > 1 else 0.0
    sd = sd if sd > 0 else max(1.0, 0.05 * mu)  # avoid division by zero on flat data
    z = (latest - mu) / sd
    if abs(z) < z_threshold:
        return []
    pct = round(abs(latest - mu) / mu * 100) if mu else 0
    direction = "below" if z < 0 else "above"
    return [
        {
            "kind": "consumption_low" if z < 0 else "consumption_high",
            "z": round(z, 2),
            "latest_g": latest,
            "baseline_g": round(mu, 1),
            "message": (
                f"Today's amount is about {pct}% {direction} the recent average. "
                "If this continues, consider mentioning it to your vet."
            ),
        }
    ]
