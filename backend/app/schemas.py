from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class Metrics(BaseModel):
    mae_mw: float | None = None
    rmse_mw: float | None = None
    bias_mw: float | None = None
    wape_percent: float | None = None
    p90_abs_error_mw: float | None = None


class Coverage(BaseModel):
    expected_hours: int
    matched_hours: int
    missing_forecast_hours: int
    missing_actual_hours: int


class Point(BaseModel):
    start_time: str
    decision_date: str
    forecast_mw: float | None = None
    actual_mw: float | None = None
    error_mw: float | None = None
    publish_time: str | None = None


class DailyRow(BaseModel):
    decision_date: str
    delivery_date: str
    publish_time: str | None = None
    matched_hours: int
    expected_hours: int
    mae_mw: float | None = None
    bias_mw: float | None = None


class AnalysisResponse(BaseModel):
    decision_start_date: str
    decision_end_date: str
    cutoff: str
    delivery_start_date: str
    delivery_end_date: str
    window_start_date: str
    window_end_date: str
    fetched_at: str
    metrics: Metrics
    coverage: Coverage
    points: list[Point]
    daily: list[DailyRow]
    warnings: list[str] = Field(default_factory=list)
