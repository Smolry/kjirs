"""Elexon BMRS retrieval and normalisation (FUELHH wind actuals, WINDFOR wind forecasts).

Endpoint contracts (per Elexon's OpenAPI spec):
  * FUELHH /stream  -> filter by settlementDateFrom / settlementDateTo (yyyy-MM-dd) + fuelType
  * WINDFOR /stream -> filter by publishDateTimeFrom / publishDateTimeTo (publication time)
The generic ``from``/``to`` parameters must NOT be used here: for WINDFOR they return only
the latest vintage rather than the historical forecasts we need. Both settlement-date and
publish-time filters cannot be combined in one request (HTTP 400).
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx

UTC = timezone.utc
CHUNK_DAYS = 7
MAX_CONCURRENCY = 4
ATTEMPTS = 3
_EPOCH = datetime.min.replace(tzinfo=UTC)


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def normalize_actuals(rows: list[dict]) -> list[dict]:
    """WIND rows only. If an interval is reported twice, the latest publishTime wins."""
    latest: dict[datetime, tuple[datetime, float]] = {}
    for row in rows:
        if str(row.get("fuelType", "")).upper() != "WIND":
            continue
        start, generation = _parse_dt(row.get("startTime")), _num(row.get("generation"))
        if start is None or generation is None:
            continue
        published = _parse_dt(row.get("publishTime")) or _EPOCH
        if start not in latest or published >= latest[start][0]:
            latest[start] = (published, generation)
    return [{"start_time": s.isoformat(), "generation_mw": g} for s, (_, g) in sorted(latest.items())]


def normalize_forecasts(rows: list[dict]) -> list[dict]:
    """One record per (startTime, publishTime) forecast vintage."""
    unique: dict[tuple[datetime, datetime], float] = {}
    for row in rows:
        start, publish = _parse_dt(row.get("startTime")), _parse_dt(row.get("publishTime"))
        generation = _num(row.get("generation"))
        if start is None or publish is None or generation is None:
            continue
        unique[(start, publish)] = generation
    return [
        {"start_time": s.isoformat(), "publish_time": p.isoformat(), "generation_mw": g}
        for (s, p), g in sorted(unique.items())
    ]


def date_chunks(start: date, end: date, days: int = CHUNK_DAYS) -> list[tuple[date, date]]:
    """Split an inclusive date range into inclusive chunks of at most ``days`` days."""
    chunks, current = [], start
    while current <= end:
        last = min(current + timedelta(days=days - 1), end)
        chunks.append((current, last))
        current = last + timedelta(days=1)
    return chunks


def actuals_requests(decision_start: date, decision_end: date) -> list[dict]:
    """FUELHH query params covering every delivery day (decision day + 1)."""
    first, last = decision_start + timedelta(days=1), decision_end + timedelta(days=1)
    return [
        {"settlementDateFrom": a.isoformat(), "settlementDateTo": b.isoformat(), "fuelType": "WIND"}
        for a, b in date_chunks(first, last)
    ]


def forecast_requests(decision_start: date, decision_end: date) -> list[dict]:
    """WINDFOR query params covering every vintage that could be in force at a cutoff.

    Starts the day before the first decision day so the latest earlier vintage is always
    available; ends at the end of the last decision day (cutoffs are earlier that day).
    """
    first = decision_start - timedelta(days=1)
    return [
        {"publishDateTimeFrom": f"{a.isoformat()}T00:00:00Z", "publishDateTimeTo": f"{b.isoformat()}T23:59:59Z"}
        for a, b in date_chunks(first, decision_end)
    ]


async def _get_json(client: httpx.AsyncClient, url: str, params: dict) -> list[dict]:
    failure: Exception = RuntimeError(f"Elexon request failed: {url}")
    for attempt in range(ATTEMPTS):
        try:
            response = await client.get(url, params=params, headers={"Accept": "application/json"})
        except httpx.TimeoutException:
            failure = RuntimeError(f"Elexon request timed out: {url}")
        except httpx.RequestError as exc:
            failure = RuntimeError(f"Could not reach Elexon ({url}): {exc}")
        else:
            if response.status_code >= 500:
                failure = RuntimeError(f"Elexon returned HTTP {response.status_code} for {response.url}")
            elif response.is_error:
                body = response.text[:300].replace("\n", " ")
                raise RuntimeError(f"Elexon returned HTTP {response.status_code} for {response.url}. Response: {body}")
            else:
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise RuntimeError(f"Elexon returned non-JSON content for {response.url}.") from exc
                if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    payload = payload["data"]
                if not isinstance(payload, list):
                    raise RuntimeError(
                        f"Unexpected Elexon response from {response.url}: expected an array, got {type(payload).__name__}."
                    )
                return [row for row in payload if isinstance(row, dict)]
        if attempt < ATTEMPTS - 1:
            await asyncio.sleep(0.5 * (attempt + 1))
    raise failure


async def fetch_elexon_data(
    base_url: str,
    decision_start: str,
    decision_end: str,
    timeout: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    """Fetch FUELHH wind actuals and WINDFOR forecast vintages for the decision window."""
    ds, de = date.fromisoformat(decision_start), date.fromisoformat(decision_end)
    if de < ds:
        raise ValueError("Decision end date must be on or after start date.")
    base = base_url.rstrip("/")
    actual_url, forecast_url = f"{base}/datasets/FUELHH/stream", f"{base}/datasets/WINDFOR/stream"
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, transport=transport) as client:
        async def get(url: str, params: dict) -> list[dict]:
            async with semaphore:
                return await _get_json(client, url, params)

        actual_batches, forecast_batches = await asyncio.gather(
            asyncio.gather(*(get(actual_url, p) for p in actuals_requests(ds, de))),
            asyncio.gather(*(get(forecast_url, p) for p in forecast_requests(ds, de))),
        )

    actual_raw = [row for batch in actual_batches for row in batch]
    forecast_raw = [row for batch in forecast_batches for row in batch]
    actuals, forecasts = normalize_actuals(actual_raw), normalize_forecasts(forecast_raw)
    if not actuals:
        raise RuntimeError(f"Elexon FUELHH returned no usable WIND actuals ({len(actual_raw)} rows received).")
    if not forecasts:
        raise RuntimeError(f"Elexon WINDFOR returned no usable forecasts ({len(forecast_raw)} rows received).")
    return {
        "actuals": actuals,
        "forecasts": forecasts,
        "fetched_at": datetime.now(UTC).isoformat(),
        "raw_counts": {"actuals": len(actual_raw), "forecasts": len(forecast_raw)},
    }
