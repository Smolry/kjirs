# Wind Forecast Decision Monitor

A React + FastAPI web app for a UK utility's day-ahead power-buying team. It answers two questions, using **only** national wind data from Elexon BMRS:

1. **What did the latest wind forecast say at the time the day-ahead purchase decision had to be made?**
2. **How accurate were those forecasts?** (MAE, RMSE, bias, relative error, 90th-percentile error)

Scope: purchase decisions made in **January 2026** (delivery 2 Jan – 1 Feb 2026).

**Live app:** _add the Vercel URL here after deploying (see "Deploy")_

## How it works

| Data | Elexon dataset | Request | Resolution |
|---|---|---|---|
| Actual wind | `FUELHH`, `fuelType=WIND` | `/datasets/FUELHH/stream?settlementDateFrom&settlementDateTo&fuelType=WIND` | half-hourly |
| Wind forecasts | `WINDFOR` (many vintages, each with `publishTime`) | `/datasets/WINDFOR/stream?publishDateTimeFrom&publishDateTimeTo` | hourly |

Both endpoints are called with their own documented filters (the generic `from`/`to` parameters return only the latest WINDFOR vintage, so they are not used). Requests are split into 7-day chunks and run concurrently; results are cached in memory.

**Method**

- A decision is made on day **D** at the *decision time* (default **09:20 UK time**) and covers delivery day **D+1**.
- For every delivery hour, the forecast used is the **latest WINDFOR vintage with `publishTime` ≤ decision time**. Later forecasts are never used.
- WINDFOR is hourly and FUELHH is half-hourly, so actuals are averaged to the hour (both half-hours required) before comparing.
- `error = forecast − actual`; positive means wind was over-forecast.
- Metrics are computed on hours that have both a forecast and an actual: **MAE**, **RMSE**, **bias** (mean error), **WAPE** (Σ|error| ÷ Σactual), and the **90th percentile of |error|**. The number of evaluated hours is always shown.

**Assumptions (adjustable in the UI or `backend/.env`)**

- The brief only says decisions are made "one day before delivery". The default decision time of **09:20** is the EPEX GB hourly day-ahead gate closure (the earliest GB day-ahead auction; N2EX closes at 09:50).
- Times are UTC, which equals UK local time in January (no daylight-saving handling is needed for this window).

## Run locally

**With Docker**
```bash
docker compose up --build
```
Frontend: http://localhost:5173 · Backend API docs: http://localhost:8000/docs

**Without Docker**
```bash
# backend (Python 3.11+)
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # Windows: copy .env.example .env
uvicorn app.main:app --reload --port 8000

# frontend (Node 20+), second terminal
cd frontend
npm install
cp .env.example .env                                   # Windows: copy .env.example .env
npm run dev
```
The first request downloads the data from Elexon (a few seconds); later requests are served from cache. **Refresh data** forces a re-download.

## Tests
```bash
cd backend
pip install -r requirements-dev.txt
pytest
```
Tests cover forecast selection (cutoff rules), hourly alignment, metrics, API validation and caching, and the Elexon client. The client tests run against an in-process mock that returns HTTP 400 unless the documented query parameters are used.

## API
| Endpoint | Description |
|---|---|
| `GET /api/analysis?start=&end=&cutoff=` | Decision dates (`YYYY-MM-DD`, within January 2026) and decision time (`HH:MM`, UK). Returns metrics, coverage, hourly points and a per-decision summary. Defaults: all of January, 09:20. |
| `POST /api/refresh` | Discard cached Elexon data and re-download. |
| `GET /api/health` | Liveness. |

If Elexon is unreachable or returns an unexpected response, the API answers `502` with the reason and the UI shows it. No synthetic data is ever substituted.

## Files and directories
```text
backend/
  app/main.py          FastAPI app, CORS
  app/config.py        environment settings
  app/data_source.py   Elexon requests (chunked, retried) and normalisation
  app/analytics.py     decision-time forecast selection and error metrics
  app/cache.py         in-memory (optionally file) cache with TTL
  app/schemas.py       response models
  app/api/routes.py    endpoints
  tests/               pytest suite + strict mock of the Elexon endpoints
  Dockerfile, requirements*.txt, .env.example
frontend/
  src/App.tsx          dashboard (filters, metrics, tables)
  src/charts.tsx       forecast vs actual and error charts (Recharts)
  src/api.ts           typed API client
  src/format.ts        number/date formatting
  src/styles.css
  Dockerfile, package.json, .env.example
docker-compose.yml
```


## AI tools disclosure
This project was built with AI assistance (Claude by Anthropic) for implementation specifically for boiler plate frontend, tests and documentation. Endpoint parameters were checked against Elexon's published API documentation, and the code was tested as described above.
