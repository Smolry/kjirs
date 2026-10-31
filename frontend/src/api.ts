const BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

export type Point = {
  start_time: string
  decision_date: string
  forecast_mw: number | null
  actual_mw: number | null
  error_mw: number | null
  publish_time: string | null
}

export type DailyRow = {
  decision_date: string
  delivery_date: string
  publish_time: string | null
  matched_hours: number
  expected_hours: number
  mae_mw: number | null
  bias_mw: number | null
}

export type Analysis = {
  decision_start_date: string
  decision_end_date: string
  cutoff: string
  delivery_start_date: string
  delivery_end_date: string
  window_start_date: string
  window_end_date: string
  fetched_at: string
  metrics: {
    mae_mw: number | null
    rmse_mw: number | null
    bias_mw: number | null
    wape_percent: number | null
    p90_abs_error_mw: number | null
  }
  coverage: { expected_hours: number; matched_hours: number; missing_forecast_hours: number; missing_actual_hours: number }
  points: Point[]
  daily: DailyRow[]
  warnings: string[]
}

export type Query = { start?: string; end?: string; cutoff?: string }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, init)
  } catch {
    throw new Error(`Cannot reach the API at ${BASE}. Is the backend running?`)
  }
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      /* keep the status text */
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const api = {
  analysis: (query: Query = {}) => {
    const params = new URLSearchParams()
    Object.entries(query).forEach(([k, v]) => v && params.set(k, v))
    const qs = params.toString()
    return request<Analysis>(`/api/analysis${qs ? `?${qs}` : ''}`)
  },
  refresh: () => request<{ status: string }>('/api/refresh', { method: 'POST' }),
}
