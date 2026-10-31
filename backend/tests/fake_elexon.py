"""In-process stand-in for the Elexon stream endpoints used by tests.

It enforces the real parameter contract: a request using anything other than the documented
filters answers HTTP 400, so tests fail if the client regresses to generic from/to params.
"""
from datetime import date, datetime, timedelta, timezone

import httpx


def _z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_rows(first_delivery: date, last_delivery: date, publish_hours=(7, 9)):
    """Half-hourly FUELHH wind rows and hourly WINDFOR vintages (two per day)."""
    actuals, forecasts = [], []
    t = datetime.combine(first_delivery, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(last_delivery + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    while t < end:
        actuals.append({"fuelType": "WIND", "startTime": _z(t), "generation": 1000 + t.hour, "publishTime": _z(t)})
        actuals.append({"fuelType": "CCGT", "startTime": _z(t), "generation": 5000})
        t += timedelta(minutes=30)
    day = first_delivery - timedelta(days=3)
    while day <= last_delivery:
        for h in publish_hours:
            published = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=h, minutes=30)
            for k in range(73):
                target = published.replace(minute=0) + timedelta(hours=k + 1)
                forecasts.append({"publishTime": _z(published), "startTime": _z(target), "generation": 1100 + h})
        day += timedelta(days=1)
    return actuals, forecasts


def make_transport(first_delivery: date, last_delivery: date, requests_log: list | None = None):
    actuals, forecasts = build_rows(first_delivery, last_delivery)

    def handler(request: httpx.Request) -> httpx.Response:
        q = dict(request.url.params)
        if requests_log is not None:
            requests_log.append((request.url.path, q))
        if request.url.path.endswith("/datasets/FUELHH/stream"):
            if set(q) != {"settlementDateFrom", "settlementDateTo", "fuelType"} or q["fuelType"] != "WIND":
                return httpx.Response(400, json={"error": "bad FUELHH params"})
            lo, hi = date.fromisoformat(q["settlementDateFrom"]), date.fromisoformat(q["settlementDateTo"])
            rows = [r for r in actuals if lo <= date.fromisoformat(r["startTime"][:10]) <= hi and r["fuelType"] == "WIND"]
            return httpx.Response(200, json=rows)
        if request.url.path.endswith("/datasets/WINDFOR/stream"):
            if set(q) != {"publishDateTimeFrom", "publishDateTimeTo"}:
                return httpx.Response(400, json={"error": "bad WINDFOR params"})
            lo = datetime.fromisoformat(q["publishDateTimeFrom"].replace("Z", "+00:00"))
            hi = datetime.fromisoformat(q["publishDateTimeTo"].replace("Z", "+00:00"))
            rows = [r for r in forecasts if lo <= datetime.fromisoformat(r["publishTime"].replace("Z", "+00:00")) <= hi]
            return httpx.Response(200, json=rows)
        return httpx.Response(404)

    return httpx.MockTransport(handler)
