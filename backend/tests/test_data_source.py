import asyncio
from datetime import date

import pytest

from app.data_source import (
    actuals_requests,
    date_chunks,
    fetch_elexon_data,
    forecast_requests,
    normalize_actuals,
    normalize_forecasts,
)
from tests.fake_elexon import make_transport


def test_date_chunks_are_inclusive_and_contiguous():
    chunks = date_chunks(date(2026, 1, 2), date(2026, 2, 1), days=7)
    assert chunks[0] == (date(2026, 1, 2), date(2026, 1, 8))
    assert chunks[-1] == (date(2026, 1, 30), date(2026, 2, 1))
    assert sum((b - a).days + 1 for a, b in chunks) == 31


def test_actuals_requests_use_settlement_dates_for_delivery_days():
    reqs = actuals_requests(date(2026, 1, 1), date(2026, 1, 31))
    assert reqs[0]["settlementDateFrom"] == "2026-01-02"
    assert reqs[-1]["settlementDateTo"] == "2026-02-01"
    assert all(set(r) == {"settlementDateFrom", "settlementDateTo", "fuelType"} and r["fuelType"] == "WIND" for r in reqs)


def test_forecast_requests_use_publish_time_from_day_before_first_decision():
    reqs = forecast_requests(date(2026, 1, 1), date(2026, 1, 31))
    assert reqs[0]["publishDateTimeFrom"] == "2025-12-31T00:00:00Z"
    assert reqs[-1]["publishDateTimeTo"] == "2026-01-31T23:59:59Z"
    assert all(set(r) == {"publishDateTimeFrom", "publishDateTimeTo"} for r in reqs)


def test_normalize_actuals_keeps_only_wind_and_latest_revision():
    rows = normalize_actuals([
        {"fuelType": "WIND", "startTime": "2026-01-02T00:00:00Z", "generation": 1200, "publishTime": "2026-01-02T00:30:00Z"},
        {"fuelType": "WIND", "startTime": "2026-01-02T00:00:00Z", "generation": 1250, "publishTime": "2026-01-02T01:00:00Z"},
        {"fuelType": "CCGT", "startTime": "2026-01-02T00:00:00Z", "generation": 900},
        {"fuelType": "WIND", "startTime": "2026-01-02T00:30:00Z", "generation": None},
    ])
    assert rows == [{"start_time": "2026-01-02T00:00:00+00:00", "generation_mw": 1250.0}]


def test_normalize_forecasts_requires_publish_time_and_dedupes():
    rows = normalize_forecasts([
        {"startTime": "2026-01-02T00:00:00Z", "publishTime": "2026-01-01T07:30:00Z", "generation": 1300},
        {"startTime": "2026-01-02T00:00:00Z", "publishTime": "2026-01-01T07:30:00Z", "generation": 1300},
        {"startTime": "2026-01-02T00:00:00Z", "generation": 1300},
    ])
    assert rows == [{"start_time": "2026-01-02T00:00:00+00:00", "publish_time": "2026-01-01T07:30:00+00:00", "generation_mw": 1300.0}]


def test_fetch_uses_documented_params_and_returns_data():
    log: list = []
    transport = make_transport(date(2026, 1, 2), date(2026, 2, 1), log)
    data = asyncio.run(fetch_elexon_data("https://elexon.test/api/v1", "2026-01-01", "2026-01-31", 5, transport))
    assert len(data["actuals"]) == 31 * 48
    assert data["forecasts"]
    assert {p.split("/")[-2] for p, _ in log} == {"FUELHH", "WINDFOR"}


def test_fetch_surfaces_elexon_errors():
    import httpx

    transport = httpx.MockTransport(lambda request: httpx.Response(400, text="nope"))
    with pytest.raises(RuntimeError, match="HTTP 400"):
        asyncio.run(fetch_elexon_data("https://elexon.test/api/v1", "2026-01-01", "2026-01-03", 5, transport))
