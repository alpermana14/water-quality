import { Activity, Droplets, GitBranch, TrendingUp } from 'lucide-react'
import { formatTime } from '../api'

export const VIEWS = [
  { key: 'forecast', label: 'Forecast', icon: TrendingUp },
  { key: 'anomalies', label: 'Anomalies', icon: Activity },
  { key: 'influence', label: 'Lag influence', icon: GitBranch },
]

function Fact({ label, value }) {
  return (
    <div className="flex justify-between gap-3">
      <dt>{label}</dt>
      <dd className="tnum text-right text-white">{value}</dd>
    </div>
  )
}

export default function Sidebar({ view, onView, status }) {
  const model = status?.model
  return (
    <aside
      className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col px-3 py-4 lg:flex"
      style={{ background: 'var(--nav)', color: 'var(--nav-ink)' }}
    >
      <div className="flex items-center gap-2.5 px-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-md" style={{ background: '#2a78d6' }}>
          <Droplets size={18} color="#ffffff" aria-hidden />
        </span>
        <div className="leading-tight">
          <div className="text-sm font-semibold text-white">Water Quality</div>
          <div className="text-xs">Monitoring</div>
        </div>
      </div>

      <nav className="mt-6 space-y-1" aria-label="Views">
        {VIEWS.map(({ key, label, icon: Icon }) => {
          const active = view === key
          return (
            <button
              key={key} onClick={() => onView(key)} aria-current={active ? 'page' : undefined}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm"
              style={active ? { background: 'var(--nav-active)', color: '#ffffff' } : undefined}
            >
              <Icon size={16} aria-hidden />
              {label}
            </button>
          )
        })}
      </nav>

      {model && (
        <dl className="mt-auto space-y-1.5 border-t border-white/10 px-2 pt-4 text-xs">
          <div className="mb-2 font-medium text-white">Forecast model</div>
          <Fact label="Trained" value={formatTime(model.trained_at, true)} />
          <Fact label="History" value={`${model.history_days} days`} />
          <Fact label="Backtest" value={`${Math.round(model.holdout_hours)} hours`} />
          <Fact label="Models" value={model.models} />
        </dl>
      )}
    </aside>
  )
}
