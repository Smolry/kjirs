export const fmt = (v: number | null | undefined, digits = 0) =>
  v == null || !Number.isFinite(v)
    ? '—'
    : v.toLocaleString('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: digits })

export const signed = (v: number | null | undefined, digits = 0) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${fmt(v, digits)}`

const DAY_MS = 24 * 3600 * 1000

export const dayLabel = (t: number) =>
  new Date(t).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' })

export const dateTimeLabel = (t: number) =>
  `${new Date(t).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' })} ` +
  `${new Date(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC`

export const publishLabel = (iso: string | null) => (iso ? dateTimeLabel(Date.parse(iso)) : '—')

/** Midnight-UTC tick positions, thinned to at most ~8 labels. */
export function dayTicks(min: number, max: number): number[] {
  const first = Math.ceil(min / DAY_MS) * DAY_MS
  const days = Math.max(1, Math.round((max - first) / DAY_MS) + 1)
  const step = Math.max(1, Math.ceil(days / 8))
  const ticks: number[] = []
  for (let t = first; t <= max; t += step * DAY_MS) ticks.push(t)
  return ticks
}
