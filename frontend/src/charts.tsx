import { useMemo } from 'react'
import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Point } from './api'
import { dateTimeLabel, dayLabel, dayTicks, fmt } from './format'

type Row = { t: number; forecast: number | null; actual: number | null; error: number | null }

function useRows(points: Point[]) {
  return useMemo(() => {
    const rows: Row[] = points.map(p => ({ t: Date.parse(p.start_time), forecast: p.forecast_mw, actual: p.actual_mw, error: p.error_mw }))
    const ticks = rows.length ? dayTicks(rows[0].t, rows[rows.length - 1].t) : []
    return { rows, ticks }
  }, [points])
}

const axisProps = (ticks: number[]) => ({
  dataKey: 't',
  type: 'number' as const,
  scale: 'time' as const,
  domain: ['dataMin', 'dataMax'] as [string, string],
  ticks,
  tickFormatter: dayLabel,
  tick: { fontSize: 11 },
})

export function ForecastChart({ points }: { points: Point[] }) {
  const { rows, ticks } = useRows(points)
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 4" vertical={false} />
          <XAxis {...axisProps(ticks)} />
          <YAxis tick={{ fontSize: 11 }} width={55} tickFormatter={v => fmt(v)} />
          <Tooltip
            labelFormatter={(t: number) => dateTimeLabel(t)}
            formatter={(v: number, name: string) => [`${fmt(v)} MW`, name]}
          />
          <Line dataKey="forecast" name="Forecast" stroke="#3b6fca" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line dataKey="actual" name="Actual" stroke="#21866e" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ErrorChart({ points }: { points: Point[] }) {
  const { rows, ticks } = useRows(points)
  return (
    <div className="chart chart-short">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 4" vertical={false} />
          <XAxis {...axisProps(ticks)} />
          <YAxis tick={{ fontSize: 11 }} width={55} tickFormatter={v => fmt(v)} />
          <Tooltip
            labelFormatter={(t: number) => dateTimeLabel(t)}
            formatter={(v: number) => [`${fmt(v)} MW`, 'Forecast − actual']}
          />
          <ReferenceLine y={0} stroke="#8b95a3" />
          <Area dataKey="error" stroke="#cb7a36" fill="#f4d9bd" fillOpacity={0.65} connectNulls={false} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
