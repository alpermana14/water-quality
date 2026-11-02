import { AlertTriangle, CheckCircle2, Info, LoaderCircle, Radio, XCircle } from 'lucide-react'
import { formatTime, zoneLabel } from '../api'
import { VIEWS } from './Sidebar'

const FRESH_MINUTES = 15

function Summary({ icon: Icon, color, children }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <Icon size={14} color={color} aria-hidden />
      {children}
    </span>
  )
}

export default function StatusBar({ title, status, episodes, view, onView }) {
  const flagged = status?.sensors?.filter((s) => ['flagged', 'flatline'].includes(s.status)).length ?? 0
  const open = episodes?.filter((e) => !e.reviewed_at).length ?? 0
  const age = status?.latest_reading ? (Date.now() - Date.parse(status.latest_reading)) / 60000 : null
  const live = age != null && age < FRESH_MINUTES

  return (
    <header className="sticky top-0 z-10 border-b border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-3 lg:px-6">
        <h1 className="text-lg font-semibold">{title}</h1>
        {status && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink2">
            {flagged > 0
              ? <Summary icon={AlertTriangle} color="var(--critical)">{flagged} sensor{flagged > 1 ? 's' : ''} flagged</Summary>
              : <Summary icon={CheckCircle2} color="var(--good)">All sensors normal</Summary>}
            {open > 0 && <Summary icon={AlertTriangle} color="var(--warning)">{open} open episode{open > 1 ? 's' : ''}</Summary>}
            <Summary icon={Radio} color={live ? 'var(--good)' : 'var(--warning)'}>
              {live ? 'Live' : 'Delayed'} · {formatTime(status.latest_reading, true)} {zoneLabel()}
            </Summary>
          </div>
        )}
      </div>
      <nav className="flex gap-1 overflow-x-auto px-3 pb-2 lg:hidden" aria-label="Views">
        {VIEWS.map(({ key, label, icon: Icon }) => (
          <button
            key={key} onClick={() => onView(key)} aria-current={view === key ? 'page' : undefined}
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm ${view === key ? 'bg-[var(--surface-2)] font-medium text-ink' : 'text-ink2'}`}
          >
            <Icon size={14} aria-hidden />
            {label}
          </button>
        ))}
      </nav>
    </header>
  )
}

function Notice({ icon: Icon, color, children }) {
  return (
    <p className="card flex items-start gap-2 px-3 py-2 text-sm" style={{ borderLeft: `3px solid ${color}` }}>
      <Icon size={16} color={color} className="mt-0.5 shrink-0" aria-hidden />
      <span>{children}</span>
    </p>
  )
}

export function Notices({ status, error }) {
  const model = status?.model
  return (
    <>
      {status?.data_source === 'synthetic' && (
        <Notice icon={AlertTriangle} color="var(--warning)">
          <strong className="font-medium">Synthetic data.</strong> These readings are generated for testing, not measured.
        </Notice>
      )}
      {error && <Notice icon={XCircle} color="var(--critical)">Cannot reach the backend: {error}</Notice>}
      {status?.last_error && <Notice icon={XCircle} color="var(--critical)">Last update failed: {status.last_error}</Notice>}
      {status?.training && <Notice icon={LoaderCircle} color="var(--series-1)">Training forecast models in the background.</Notice>}
      {status?.train_blocked && <Notice icon={Info} color="var(--series-1)">Forecasts unavailable: not enough history ({status.train_blocked}).</Notice>}
      {model?.limited_history && (
        <Notice icon={AlertTriangle} color="var(--warning)">
          <strong className="font-medium">Limited history.</strong> Trained on {model.history_days} days of data, so
          forecasts and lag influence are provisional. Models retrain nightly.
        </Notice>
      )}
    </>
  )
}
