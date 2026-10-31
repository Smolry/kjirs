from datetime import date

import pytest
from fastapi.testclient import TestClient

import app.api.routes as routes
from app.main import app
from tests.fake_elexon import make_transport


@pytest.fixture()
def client(monkeypatch):
    real_fetch = routes.fetch_elexon_data
    calls = {"n": 0}

    async def fake_fetch(base_url, start, end, timeout):
        calls["n"] += 1
        return await real_fetch("https://elexon.test/api/v1", start, end, timeout, make_transport(date(2026, 1, 2), date(2026, 2, 1)))

    monkeypatch.setattr(routes, "fetch_elexon_data", fake_fetch)
    app.state.cache.clear()
    c = TestClient(app)
    c.calls = calls
    return c


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_analysis_defaults_to_full_january_and_is_cached(client):
    body = client.get("/api/analysis").json()
    assert (body["decision_start_date"], body["decision_end_date"], body["cutoff"]) == ("2026-01-01", "2026-01-31", "09:20")
    assert (body["delivery_start_date"], body["delivery_end_date"]) == ("2026-01-02", "2026-02-01")
    assert body["coverage"]["expected_hours"] == 31 * 24
    assert body["coverage"]["matched_hours"] == 31 * 24
    assert body["metrics"]["mae_mw"] is not None
    client.get("/api/analysis?cutoff=10:00&start=2026-01-05&end=2026-01-06")
    assert client.calls["n"] == 1  # changing the query re-uses the cached source data


def test_cutoff_changes_the_vintage_selected(client):
    early = client.get("/api/analysis?start=2026-01-10&end=2026-01-10&cutoff=09:20").json()
    late = client.get("/api/analysis?start=2026-01-10&end=2026-01-10&cutoff=09:50").json()
    assert early["daily"][0]["publish_time"] == "2026-01-10T07:30:00Z"
    assert late["daily"][0]["publish_time"] == "2026-01-10T09:30:00Z"


@pytest.mark.parametrize("query", [
    "start=2026-01-10&end=2026-01-09",
    "start=2025-12-31",
    "end=2026-02-01",
    "cutoff=25:99",
    "start=not-a-date",
])
def test_analysis_rejects_invalid_parameters(client, query):
    assert client.get(f"/api/analysis?{query}").status_code == 422


def test_upstream_failure_is_reported_as_502(client, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("Elexon down")

    monkeypatch.setattr(routes, "fetch_elexon_data", boom)
    r = client.get("/api/analysis")
    assert r.status_code == 502 and "Elexon down" in r.json()["detail"]


def test_refresh_refetches(client):
    client.get("/api/analysis")
    assert client.post("/api/refresh").json()["status"] == "refreshed"
    assert client.calls["n"] == 2
