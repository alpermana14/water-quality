import { useState } from 'react'
import { BarChart3, CheckCircle2, Info, MinusCircle, Table2, XCircle } from 'lucide-react'
import { formatDate, formatTime, reliability } from '../api'

/* Every chart has a table twin, so no value depends on hovering or on colour. */
export default function ChartCard({ title, subtitle, info, columns, rows, legend, children }) {
  const [asTable, setAsTable] = useState(false)
  const [showInfo, setShowInfo] = useState(false)
  return (
    <section className="card min-w-0">
      <div className="flex items-start justify-between gap-4 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-ink2">{subtitle}</p>}
        </div>
        <div className="flex shrink-0 gap-1">
          {info && (
            <button className="control" onClick={() => setShowInfo(!showInfo)} aria-expanded={showInfo} aria-label={`About: ${title}`}>
              <Info size={14} aria-hidden />
            </button>
          )}
          {rows && (
            <button className="control" onClick={() => setAsTable(!asTable)} aria-label={asTable ? 'Show chart' : 'Show table'}>
              {asTable ? <BarChart3 size={14} aria-hidden /> : <Table2 size={14} aria-hidden />}
            </button>
          )}
        </div>
      </div>
      {showInfo && <p className="border-b border-line bg-[var(--surface-2)] px-4 py-2 text-xs text-ink2">{info}</p>}
      <div className="p-4">
        {legend && !asTable && <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink2">{legend}</div>}
        {asTable ? (
          <div className="max-h-96 overflow-auto">
            <table className="tnum w-full text-left text-sm">
              <thead className="sticky top-0 bg-surface text-xs text-ink2">
                <tr>{columns.map((c) => <th key={c} className="py-1 pr-4 font-medium">{c}</th>)}</tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i} className="border-t border-line">
                    {row.map((cell, j) => <td key={j} className="py-1 pr-4">{cell}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : children}
      </div>
    </section>
  )
}

export function LegendKey({ color, label }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden className="inline-block h-0.5 w-4 rounded" style={{ background: color }} />
      {label}
    </span>
  )
}

export function LegendSwatch({ color, label }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden className="inline-block h-3 w-4 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  )
}

export function Stat({ label, value, unit, note }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-ink2">{label}</div>
      <div className="mt-0.5 text-xl font-semibold">{value} <span className="text-xs font-normal text-ink2">{unit}</span></div>
      {note && <div className="text-xs text-ink2">{note}</div>}
    </div>
  )
}

const RELIABILITY = {
  good: { icon: CheckCircle2, color: 'var(--good)' },
  neutral: { icon: MinusCircle, color: 'var(--muted)' },
  poor: { icon: XCircle, color: 'var(--critical)' },
  unknown: { icon: MinusCircle, color: 'var(--muted)' },
}

export function ReliabilityChip({ skill }) {
  const r = reliability(skill)
  const { icon: Icon, color } = RELIABILITY[r.key]
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap rounded border border-line px-1.5 py-0.5 text-xs text-ink2">
      <Icon size={12} color={color} aria-hidden />
      {r.label}
    </span>
  )
}

export function Segmented({ label, options, value, onChange }) {
  return (
    <div role="group" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-md border border-line bg-[var(--surface-2)] p-0.5">
      {options.map(([key, text]) => (
        <button
          key={key} onClick={() => onChange(key)} aria-pressed={value === key}
          className={`shrink-0 whitespace-nowrap rounded px-2 py-1 text-xs sm:px-2.5 ${value === key ? 'bg-surface font-medium text-ink shadow-sm' : 'text-ink2'}`}
        >
          {text}
        </button>
      ))}
    </div>
  )
}

export const HORIZONS = [[1, '5 min'], [3, '15 min'], [6, '30 min'], [12, '1 h'], [24, '2 h'], [36, '3 h']]

export function ChartTooltip({ active, payload, label, format, unit }) {
  if (!active || !payload?.length) return null
  return (
    <div className="card px-2 py-1.5 text-xs shadow-sm">
      <div className="text-ink2">{format(label)}</div>
      {payload.filter((p) => p.value != null && !Array.isArray(p.value)).map((p) => (
        <div key={p.dataKey?.toString() ?? p.name} className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-0.5 w-3 rounded" style={{ background: p.stroke }} />
          <span className="text-ink2">{p.name}</span>
          <span className="tnum ml-auto pl-3 text-ink">{p.value}{unit ? ` ${unit}` : ''}</span>
        </div>
      ))}
    </div>
  )
}

export const AXIS = {
  tick: { fill: 'var(--muted)', fontSize: 11 },
  stroke: 'var(--axis)',
  tickLine: false,
}

export const formatTick = (v) => String(+Number(v).toPrecision(4))

/* Value axis on round steps (1, 2, 2.5 or 5 × a power of ten), with about four intervals. */
export function niceAxis(values) {
  const finite = values.filter((v) => v != null && Number.isFinite(v))
  if (!finite.length) return {}
  const min = Math.min(...finite)
  const max = Math.max(...finite)
  const rough = (max - min || Math.abs(max) || 1) / 4
  const power = 10 ** Math.floor(Math.log10(rough))
  const step = [1, 2, 2.5, 5, 10].find((m) => m * power >= rough) * power
  const low = Math.floor(min / step)
  const high = Math.ceil(max / step)
  const ticks = []
  for (let i = low; i <= high; i += 1) ticks.push(+(i * step).toPrecision(10))
  return { domain: [ticks[0], ticks[ticks.length - 1]], ticks }
}

const HOUR = 3600000
const MAX_JOINED_GAP = HOUR / 2

/* Points are dropped where nothing was measured, so an outage needs a null to stop the line. */
export function breakLongGaps(points) {
  const out = []
  points.forEach((p, i) => {
    if (i && p.t - points[i - 1].t > MAX_JOINED_GAP) out.push({ t: points[i - 1].t + 1, gapBreak: true })
    out.push(p)
  })
  return out
}

export const gapAreas = (gaps) => gaps.map((g) => ({ a: Date.parse(g.start), b: Date.parse(g.end) }))

/* Ticks on round hours, so axes read 15:00, 18:00 rather than wherever the data began. */
export function timeAxis(domain) {
  const [start, end] = domain
  const span = end - start
  const step = span <= 16 * HOUR ? 2 * HOUR : span <= 30 * HOUR ? 3 * HOUR : span <= 108 * HOUR ? 12 * HOUR : 24 * HOUR
  const ticks = []
  for (let t = Math.ceil(start / step) * step; t <= end; t += step) ticks.push(t)
  return {
    ticks,
    tickFormatter: span <= 30 * HOUR ? (t) => formatTime(t) : (t) => `${formatDate(t)} ${formatTime(t)}`,
  }
}
