"""Decision-time forecast selection and forecast-error metrics.

Rules
  * A purchase decision is made on decision day D (UK local) at the cutoff time and covers
    delivery day D+1.
  * For each delivery hour, the forecast used is the latest WINDFOR vintage with
    publishTime <= cutoff. Nothing published later is ever used.
  * WINDFOR is hourly and FUELHH is half-hourly, so actuals are averaged to the hour
    (both half-hours required) before comparison.
  * error = forecast - actual. Positive means wind was over-forecast.
"""
import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
UTC = timezone.utc
HOUR = timedelta(hours=1)


def parse_cutoff(value: str) -> time:
    try:
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    except (ValueError, AttributeError):
        raise ValueError("cutoff must be a 24-hour HH:MM time (UK local)") from None


def _z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolation percentile, q in [0, 1]."""
    if not values:
        return None
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def hourly_actuals(actuals: list[dict]) -> dict[datetime, float]:
    """Average the :00 and :30 half-hours into the hour that starts at :00."""
    halves: dict[datetime, dict[int, float]] = defaultdict(dict)
    for row in actuals:
        try:
            start, value = _dt(row["start_time"]), float(row["generation_mw"])
        except (KeyError, TypeError, ValueError):
            continue
        if start.minute in (0, 30):
            halves[start.replace(minute=0, second=0, microsecond=0)][start.minute] = value
    return {hour: (v[0] + v[30]) / 2 for hour, v in halves.items() if 0 in v and 30 in v}


def index_forecasts(forecasts: list[dict]) -> dict[datetime, list[tuple[datetime, float]]]:
    by_start: dict[datetime, list[tuple[datetime, float]]] = defaultdict(list)
    for row in forecasts:
        try:
            by_start[_dt(row["start_time"])].append((_dt(row["publish_time"]), float(row["generation_mw"])))
        except (KeyError, TypeError, ValueError):
            continue
    return by_start


def compute_metrics(errors: list[float], actuals: list[float]) -> dict:
    if not errors:
        return {"mae_mw": None, "rmse_mw": None, "bias_mw": None, "wape_percent": None, "p90_abs_error_mw": None}
    n = len(errors)
    abs_errors = [abs(e) for e in errors]
    actual_total = sum(abs(a) for a in actuals)
    return {
        "mae_mw": sum(abs_errors) / n,
        "rmse_mw": math.sqrt(sum(e * e for e in errors) / n),
        "bias_mw": sum(errors) / n,
        "wape_percent": 100 * sum(abs_errors) / actual_total if actual_total else None,
        "p90_abs_error_mw": percentile(abs_errors, 0.9),
    }


def evaluate(data: dict, decision_start: date, decision_end: date, cutoff: time) -> dict:
    if decision_end < decision_start:
        raise ValueError("decision_end must be on or after decision_start")
    actual_by_hour = hourly_actuals(data.get("actuals", []))
    forecasts = index_forecasts(data.get("forecasts", []))

    points, daily = [], []
    for offset in range((decision_end - decision_start).days + 1):
        decision_date = decision_start + timedelta(days=offset)
        delivery_date = decision_date + timedelta(days=1)
        cutoff_utc = datetime.combine(decision_date, cutoff, tzinfo=UK).astimezone(UTC)
        hour = datetime.combine(delivery_date, time.min, tzinfo=UK).astimezone(UTC)
        day_end = datetime.combine(delivery_date + timedelta(days=1), time.min, tzinfo=UK).astimezone(UTC)

        day_points = []
        while hour < day_end:
            eligible = [v for v in forecasts.get(hour, []) if v[0] <= cutoff_utc]
            published, forecast = max(eligible, key=lambda v: v[0]) if eligible else (None, None)
            actual = actual_by_hour.get(hour)
            day_points.append({
                "start_time": _z(hour),
                "decision_date": decision_date.isoformat(),
                "forecast_mw": forecast,
                "actual_mw": actual,
                "error_mw": forecast - actual if forecast is not None and actual is not None else None,
                "publish_time": _z(published) if published else None,
            })
            hour += HOUR
        points.extend(day_points)

        day_matched = [p for p in day_points if p["error_mw"] is not None]
        day_metrics = compute_metrics([p["error_mw"] for p in day_matched], [p["actual_mw"] for p in day_matched])
        publish_times = [p["publish_time"] for p in day_points if p["publish_time"]]
        daily.append({
            "decision_date": decision_date.isoformat(),
            "delivery_date": delivery_date.isoformat(),
            "publish_time": max(publish_times) if publish_times else None,
            "matched_hours": len(day_matched),
            "expected_hours": len(day_points),
            "mae_mw": day_metrics["mae_mw"],
            "bias_mw": day_metrics["bias_mw"],
        })

    matched = [p for p in points if p["error_mw"] is not None]
    warnings = []
    if not matched:
        warnings.append("No hours have both a forecast published by the cutoff and an actual value.")
    elif len(matched) < len(points):
        warnings.append(f"{len(points) - len(matched)} of {len(points)} delivery hours could not be evaluated (missing forecast or actual).")
    return {
        "points": points,
        "daily": daily,
        "metrics": compute_metrics([p["error_mw"] for p in matched], [p["actual_mw"] for p in matched]),
        "coverage": {
            "expected_hours": len(points),
            "matched_hours": len(matched),
            "missing_forecast_hours": sum(p["forecast_mw"] is None for p in points),
            "missing_actual_hours": sum(p["actual_mw"] is None for p in points),
        },
        "warnings": warnings,
        "delivery_start_date": (decision_start + timedelta(days=1)).isoformat(),
        "delivery_end_date": (decision_end + timedelta(days=1)).isoformat(),
    }
