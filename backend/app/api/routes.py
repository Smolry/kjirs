from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.analytics import evaluate, parse_cutoff
from app.data_source import fetch_elexon_data
from app.schemas import AnalysisResponse, HealthResponse

router = APIRouter(prefix="/api")


async def load_data(request: Request, force_refresh: bool = False) -> dict:
    """Return the source data for the configured window (cached; one fetch at a time)."""
    state, s = request.app.state, request.app.state.settings
    key = f"elexon_{s.decision_start_date}_{s.decision_end_date}"
    async with state.data_lock:
        if not force_refresh:
            cached = state.cache.get(key)
            if cached is not None:
                return cached
        try:
            data = await fetch_elexon_data(
                s.elexon_base_url, s.decision_start_date, s.decision_end_date, s.http_timeout_seconds
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Unable to load Elexon data: {exc}") from exc
        state.cache.set(key, data)
        return data


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@router.get("/analysis", response_model=AnalysisResponse)
async def analysis(
    request: Request,
    start: str | None = Query(None, description="First decision date, YYYY-MM-DD"),
    end: str | None = Query(None, description="Last decision date, YYYY-MM-DD"),
    cutoff: str | None = Query(None, description="Decision time on the decision date, HH:MM UK local"),
):
    s = request.app.state.settings
    window_start, window_end = date.fromisoformat(s.decision_start_date), date.fromisoformat(s.decision_end_date)
    try:
        ds = date.fromisoformat(start) if start else window_start
        de = date.fromisoformat(end) if end else window_end
        cutoff_time = parse_cutoff(cutoff or s.decision_cutoff)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if de < ds:
        raise HTTPException(status_code=422, detail="end must be on or after start")
    if ds < window_start or de > window_end:
        raise HTTPException(status_code=422, detail=f"Decision dates must be within {window_start} to {window_end}")

    data = await load_data(request)
    result = evaluate(data, ds, de, cutoff_time)
    return AnalysisResponse(
        decision_start_date=ds.isoformat(),
        decision_end_date=de.isoformat(),
        cutoff=f"{cutoff_time:%H:%M}",
        window_start_date=window_start.isoformat(),
        window_end_date=window_end.isoformat(),
        fetched_at=data.get("fetched_at", ""),
        **result,
    )


@router.post("/refresh")
async def refresh(request: Request):
    """Discard the cached source data and re-download it from Elexon."""
    data = await load_data(request, force_refresh=True)
    return {"status": "refreshed", "fetched_at": data.get("fetched_at"), "raw_counts": data.get("raw_counts", {})}
