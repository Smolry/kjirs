import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CalendarRange, RefreshCw } from 'lucide-react'
import { api, type Analysis } from './api'
import { ErrorChart, ForecastChart } from './charts'
import { fmt, publishLabel, signed } from './format'

function Metric({ label, value, unit, note }: { label: string; value: string; unit?: string; note: string }) {
  return (
    <article className="metric">
      <span className="metric-label">{label}</span>
      <div className="metric-value">
        {value}
        {unit && value !== '—' && <small>{unit}</small>}
      </div>
      <p>{note}</p>
    </article>
  )
}

export default function App() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ start: '2026-01-01', end: '2026-01-31', cutoff: '09:20' })
  const latest = useRef(0)

  const load = useCallback(async (query: { start?: string; end?: string; cutoff?: string } = {}) => {
    const id = ++latest.current
    setLoading(true)
    setError('')
    try {
      const result = await api.analysis(query)
      if (id !== latest.current) return
      setAnalysis(result)
      setForm({ start: result.decision_start_date, end: result.decision_end_date, cutoff: result.cutoff })
    } catch (e) {
      if (id !== latest.current) return
      setError(e instanceof Error ? e.message : 'Unable to load data')
    } finally {
      if (id === latest.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function refresh() {
    setRefreshing(true)
    setError('')
    try {
      await api.refresh()
      await load(form)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }

  const minDate = analysis?.window_start_date ?? '2026-01-01'
  const maxDate = analysis?.window_end_date ?? '2026-01-31'
  const invalid = !form.start || !form.end || !form.cutoff || form.start > form.end || form.start < minDate || form.end > maxDate
  const m = analysis?.metrics
  const c = analysis?.coverage

  return (
    <main className="dashboard">
      <header className="page-header">
        <div>
          <p className="eyebrow">DAY-AHEAD WIND FORECAST MONITOR</p>
          <h1>Wind forecast vs actual generation</h1>
          <p className="subtitle">
            Great Britain national wind · what the forecast said when the day-ahead purchase decision had to be made, and how accurate it proved.
          </p>
        </div>
        <button className="refresh" onClick={() => void refresh()} disabled={loading || refreshing}>
          <RefreshCw size={16} className={refreshing ? 'spin' : ''} /> Refresh data
        </button>
      </header>

      <section className="filters panel">
        <div className="filter-title">
          <CalendarRange size={18} />
          <div>
            <h2>Purchase decisions</h2>
            <p>Decisions made on these dates, for delivery the following day.</p>
          </div>
        </div>
        <label>
          First decision date
          <input type="date" min={minDate} max={maxDate} value={form.start} onChange={e => setForm({ ...form, start: e.target.value })} />
        </label>
        <label>
          Last decision date
          <input type="date" min={minDate} max={maxDate} value={form.end} onChange={e => setForm({ ...form, end: e.target.value })} />
        </label>
        <label>
          Decision time (UK)
          <input type="time" value={form.cutoff} onChange={e => setForm({ ...form, cutoff: e.target.value })} />
        </label>
        <button className="primary" onClick={() => void load(form)} disabled={invalid || loading}>
          Analyze
        </button>
        {invalid && form.start > form.end && <p className="range-error">The first decision date must be on or before the last.</p>}
      </section>

      {error && (
        <div className="notice danger" role="alert">
          <AlertTriangle size={17} />
          <span>
            <b>Could not load data:</b> {error}
          </span>
          <button onClick={() => void load(form)}>Retry</button>
        </div>
      )}
      {analysis?.warnings.map(w => (
        <div className="notice" key={w}>
          <AlertTriangle size={17} />
          <span>{w}</span>
        </div>
      ))}
      {loading && (
        <div className="loading-state" role="status" aria-live="polite">
          <span className="loading-spinner" />
          <span>Loading Elexon wind data — the first load can take a few seconds…</span>
        </div>
      )}

      {analysis && (
        <>
          <p className="context">
            For each hour delivered on <b>{analysis.delivery_start_date}</b> to <b>{analysis.delivery_end_date}</b>, the forecast shown is the latest one
            published by <b>{analysis.cutoff}</b> (UK time) on the previous day — the information available at the time of the decision. Times are UTC
            (identical to UK time in January).
          </p>

          <section className="metrics">
            <Metric label="Mean absolute error (MAE)" value={fmt(m?.mae_mw)} unit=" MW" note="Typical size of the forecast miss, in either direction." />
            <Metric label="Root mean square error (RMSE)" value={fmt(m?.rmse_mw)} unit=" MW" note="Like MAE but weights large misses more." />
            <Metric label="Bias (mean error)" value={signed(m?.bias_mw)} unit=" MW" note="Positive: wind over-forecast on average. Negative: under-forecast." />
            <Metric label="Relative error (WAPE)" value={fmt(m?.wape_percent, 1)} unit="%" note="Total absolute error as a share of total actual generation." />
            <Metric label="90th percentile abs. error" value={fmt(m?.p90_abs_error_mw)} unit=" MW" note="In 9 of 10 hours the miss was no bigger than this." />
            <Metric
              label="Hours evaluated"
              value={c ? `${c.matched_hours.toLocaleString('en-GB')} / ${c.expected_hours.toLocaleString('en-GB')}` : '—'}
              note="Delivery hours with both a decision-time forecast and an actual."
            />
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Decision-time forecast vs actual wind generation</h2>
                <p>Hourly · MW</p>
              </div>
              <div className="legend">
                <span><i className="forecast-dot" /> Forecast</span>
                <span><i className="actual-dot" /> Actual</span>
              </div>
            </div>
            {analysis.points.length ? <ForecastChart points={analysis.points} /> : <div className="empty-chart">No data for this selection.</div>}
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Forecast error</h2>
                <p>Forecast − actual · positive means wind was over-forecast (less wind than expected, so more power to buy elsewhere)</p>
              </div>
            </div>
            {analysis.points.length ? <ErrorChart points={analysis.points} /> : <div className="empty-chart">No error values available.</div>}
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Forecast used for each decision</h2>
                <p>The latest forecast available at the decision time, and how it performed.</p>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Decision date</th>
                    <th>Delivery date</th>
                    <th>Forecast published (UTC)</th>
                    <th className="num">Hours evaluated</th>
                    <th className="num">MAE (MW)</th>
                    <th className="num">Bias (MW)</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.daily.map(d => (
                    <tr key={d.decision_date}>
                      <td>{d.decision_date}</td>
                      <td>{d.delivery_date}</td>
                      <td>{publishLabel(d.publish_time)}</td>
                      <td className="num">{d.matched_hours} / {d.expected_hours}</td>
                      <td className="num">{fmt(d.mae_mw)}</td>
                      <td className="num">{signed(d.bias_mw)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <footer>
        <span>Source: Elexon BMRS — FUELHH (actual wind) and WINDFOR (wind forecasts). Actuals are half-hourly and averaged to the forecast's hourly resolution.</span>
      </footer>
    </main>
  )
}
