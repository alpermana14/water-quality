import { useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleDot, Info } from 'lucide-react'
import { getJson, formatNumber, formatTime } from '../api'

function State({ episode }) {
  const [Icon, color, label] = episode.reviewed_at
    ? [CheckCircle2, 'var(--good)', 'Reviewed']
    : episode.currently_flagged
      ? [AlertTriangle, 'var(--critical)', 'Open, flagged now']
      : [CircleDot, 'var(--warning)', 'Open, not flagged now']
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <Icon size={14} color={color} aria-hidden />
      {label}
    </span>
  )
}

export default function EpisodePanel({ sensors, episodes, reload }) {
  const [showInfo, setShowInfo] = useState(false)
  const [reviewError, setReviewError] = useState(null)
  if (!episodes) return null
  const label = (key) => sensors.find((s) => s.key === key)?.label || key

  async function review(id) {
    let token = sessionStorage.getItem('approverToken') || ''
    if (!token) {
      token = (window.prompt('Enter your approver token:') || '').trim()
      if (!token) return
      sessionStorage.setItem('approverToken', token)
    }
    try {
      await getJson(`/api/episodes/${id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Approver-Token': token },
        body: JSON.stringify({ note: '' }),
      })
      setReviewError(null)
      reload()
    } catch (err) {
      if (err.status === 401) sessionStorage.removeItem('approverToken')
      setReviewError(err.message)
    }
  }

  return (
    <section className="card">
      <div className="flex items-center justify-between gap-4 border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold">Episodes</h2>
        <button className="control" onClick={() => setShowInfo(!showInfo)} aria-expanded={showInfo} aria-label="About episodes">
          <Info size={14} aria-hidden />
        </button>
      </div>
      {showInfo && (
        <p className="border-b border-line bg-[var(--surface-2)] px-4 py-2 text-xs text-ink2">
          An episode stays open until someone reviews it. A lasting change becomes the new normal for the score after
          about 1.5 days, so a recovered score does not mean the problem went away.
        </p>
      )}
      {reviewError && <p role="alert" className="border-b border-line px-4 py-2 text-sm text-ink">{reviewError}</p>}
      {episodes.length === 0 ? (
        <p className="p-4 text-sm text-ink2">No episodes.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="tnum w-full text-left text-sm">
            <thead className="bg-[var(--surface-2)] text-xs text-ink2">
              <tr>
                {['Sensor', 'Started', 'Last flagged', 'Lowest score', 'State', ''].map((h) => (
                  <th key={h} className="whitespace-nowrap px-4 py-2 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {episodes.map((e) => (
                <tr key={e.id} className="border-t border-line">
                  <td className="whitespace-nowrap px-4 py-2 font-medium">{label(e.sensor)}</td>
                  <td className="whitespace-nowrap px-4 py-2">{formatTime(e.started_at, true)}</td>
                  <td className="whitespace-nowrap px-4 py-2">{formatTime(e.last_flagged_at, true)}</td>
                  <td className="px-4 py-2">{formatNumber(e.min_score, 3)}</td>
                  <td className="px-4 py-2"><State episode={e} /></td>
                  <td className="px-4 py-2 text-right">
                    {!e.reviewed_at && <button className="control whitespace-nowrap" onClick={() => review(e.id)}>Mark reviewed</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
