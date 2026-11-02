import {
  AlertTriangle, CheckCircle2, Clock, HelpCircle, Hourglass, MinusCircle,
} from 'lucide-react'
import { Line, LineChart, ResponsiveContainer, YAxis } from 'recharts'
import { formatNumber } from '../api'

export const STATUS = {
  normal: { icon: CheckCircle2, label: 'Normal', color: 'var(--good)' },
  flagged: { icon: AlertTriangle, label: 'Flagged', color: 'var(--critical)' },
  stale: { icon: Clock, label: 'No recent data', color: 'var(--warning)' },
  flatline: { icon: MinusCircle, label: 'Flatline', color: 'var(--serious)' },
  undetermined: { icon: HelpCircle, label: 'Undetermined', color: 'var(--muted)' },
  insufficient_data: { icon: HelpCircle, label: 'Too many gaps', color: 'var(--muted)' },
  warming_up: { icon: Hourglass, label: 'Collecting 3 days', color: 'var(--muted)' },
}

export function StatusLabel({ status }) {
  const s = STATUS[status] || STATUS.undetermined
  const Icon = s.icon
  return (
    <span className="inline-flex items-center gap-1 text-xs text-ink2">
      <Icon size={13} color={s.color} aria-hidden />
      {s.label}
    </span>
  )
}

export default function SensorCards({ sensors, selected, onSelect }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      {sensors.map((s) => {
        const active = s.key === selected
        return (
          <button
            key={s.key} onClick={() => onSelect(s.key)} aria-pressed={active}
            className="card min-w-0 px-3 pb-2 pt-2.5 text-left"
            style={active ? { borderColor: 'var(--series-1)', boxShadow: 'inset 0 0 0 1px var(--series-1)' } : undefined}
          >
            <div className="truncate text-xs font-medium text-ink2">{s.label}</div>
            <div className="mt-1 flex flex-wrap items-baseline justify-between gap-x-2">
              <span className="whitespace-nowrap text-2xl font-semibold">
                {formatNumber(s.value, 2)} <span className="text-xs font-normal text-ink2">{s.unit}</span>
              </span>
              <StatusLabel status={s.status} />
            </div>
            <div className="mt-1 h-7" aria-hidden>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={s.spark.map((y, i) => ({ i, y }))} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
                  <YAxis hide domain={['dataMin', 'dataMax']} />
                  <Line dataKey="y" stroke="var(--series-1)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </button>
        )
      })}
    </div>
  )
}
