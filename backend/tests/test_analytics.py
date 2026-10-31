from datetime import date, time

import pytest

from app.analytics import evaluate, hourly_actuals, parse_cutoff, percentile


def actual(ts, mw):
    return {"start_time": ts, "generation_mw": mw}


def fc(start, publish, mw):
    return {"start_time": start, "publish_time": publish, "generation_mw": mw}


def one_hour_data(forecasts, actual_a=100, actual_b=120):
    return {
        "actuals": [actual("2026-01-02T00:00:00+00:00", actual_a), actual("2026-01-02T00:30:00+00:00", actual_b)],
        "forecasts": forecasts,
    }


def run(data, cutoff="09:20", start=date(2026, 1, 1), end=date(2026, 1, 1)):
    return evaluate(data, start, end, parse_cutoff(cutoff))


def first(result):
    return result["points"][0]


def test_latest_forecast_published_at_or_before_cutoff_is_used():
    data = one_hour_data([
        fc("2026-01-02T00:00:00+00:00", "2026-01-01T04:30:00+00:00", 80),
        fc("2026-01-02T00:00:00+00:00", "2026-01-01T07:30:00+00:00", 130),
        fc("2026-01-02T00:00:00+00:00", "2026-01-01T09:30:00+00:00", 999),  # after 09:20
    ])
    p = first(run(data))
    assert p["forecast_mw"] == 130 and p["publish_time"] == "2026-01-01T07:30:00Z"


def test_cutoff_is_inclusive_and_later_vintage_is_picked_when_cutoff_moves():
    data = one_hour_data([
        fc("2026-01-02T00:00:00+00:00", "2026-01-01T07:30:00+00:00", 130),
        fc("2026-01-02T00:00:00+00:00", "2026-01-01T09:30:00+00:00", 140),
    ])
    assert first(run(data, "09:30"))["forecast_mw"] == 140
    assert first(run(data, "09:29"))["forecast_mw"] == 130


def test_no_forecast_before_cutoff_means_unmatched_hour():
    data = one_hour_data([fc("2026-01-02T00:00:00+00:00", "2026-01-01T09:30:00+00:00", 140)])
    r = run(data)
    assert first(r)["forecast_mw"] is None and first(r)["error_mw"] is None
    assert r["metrics"]["mae_mw"] is None
    assert r["warnings"]


def test_actuals_are_averaged_to_the_hour_and_error_is_forecast_minus_actual():
    data = one_hour_data([fc("2026-01-02T00:00:00+00:00", "2026-01-01T07:30:00+00:00", 130)])
    p = first(run(data))
    assert p["actual_mw"] == 110  # mean(100, 120)
    assert p["error_mw"] == 20  # over-forecast is positive


def test_hour_with_a_single_half_hour_is_not_evaluated():
    assert hourly_actuals([actual("2026-01-02T00:00:00+00:00", 100)]) == {}


def test_metrics_and_coverage():
    actuals, forecasts = [], []
    for hour, (a, f) in enumerate([(100, 110), (200, 180), (300, 300), (400, 460)]):
        for minute in ("00", "30"):
            actuals.append(actual(f"2026-01-02T{hour:02d}:{minute}:00+00:00", a))
        forecasts.append(fc(f"2026-01-02T{hour:02d}:00:00+00:00", "2026-01-01T07:30:00+00:00", f))
    r = run({"actuals": actuals, "forecasts": forecasts})
    m = r["metrics"]
    assert m["mae_mw"] == pytest.approx((10 + 20 + 0 + 60) / 4)
    assert m["bias_mw"] == pytest.approx((10 - 20 + 0 + 60) / 4)
    assert m["rmse_mw"] == pytest.approx(((100 + 400 + 0 + 3600) / 4) ** 0.5)
    assert m["wape_percent"] == pytest.approx(100 * 90 / 1000)
    assert m["p90_abs_error_mw"] == pytest.approx(percentile([10, 20, 0, 60], 0.9))
    assert r["coverage"] == {"expected_hours": 24, "matched_hours": 4, "missing_forecast_hours": 20, "missing_actual_hours": 20}


def test_decision_window_maps_to_next_day_delivery_and_covers_24_hours_each():
    r = run({"actuals": [], "forecasts": []}, start=date(2026, 1, 1), end=date(2026, 1, 3))
    assert len(r["points"]) == 72
    assert r["points"][0]["start_time"] == "2026-01-02T00:00:00Z"
    assert r["points"][-1]["start_time"] == "2026-01-04T23:00:00Z"
    assert (r["delivery_start_date"], r["delivery_end_date"]) == ("2026-01-02", "2026-01-04")
    assert [d["decision_date"] for d in r["daily"]] == ["2026-01-01", "2026-01-02", "2026-01-03"]


def test_daily_summary_reports_vintage_used():
    data = one_hour_data([fc("2026-01-02T00:00:00+00:00", "2026-01-01T07:30:00+00:00", 130)])
    day = run(data)["daily"][0]
    assert day["publish_time"] == "2026-01-01T07:30:00Z"
    assert day["matched_hours"] == 1 and day["mae_mw"] == 20


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([], 0.9) is None


@pytest.mark.parametrize("bad", ["25:00", "9", "ab:cd", "09:20:00"])
def test_parse_cutoff_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        parse_cutoff(bad)


def test_parse_cutoff_accepts_hh_mm():
    assert parse_cutoff("09:20") == time(9, 20)
