import { formatNumber, formatTime, horizonLabel, lagLabel, usePoll } from '../api'
import ChartCard, { Stat } from './ChartCard'

export default function ForecastExplain({ sensor, horizon, labelOf }) {
  const { data, error } = usePoll(`/api/explain/${sensor.key}/local?horizon=${horizon}`)
  if (error && !data) return <section className="card p-4 text-sm text-ink2">{error}</section>
  if (!data) return null

  const name = (i) => (i.sensor === 'time_of_day' ? 'Time of day' : `${labelOf(i.sensor)}, ${lagLabel(i.lag_hour)}`)
  const items = [
    { fixed: 'Typical change at this look-ahead', contribution: data.base_value },
    ...data.items,
    { fixed: 'All other inputs', contribution: data.others },
  ]
  const rowName = (i) => i.fixed || name(i)
  const biggest = Math.max(...items.map((i) => Math.abs(i.contribution)), 1e-12)
  const signed = (v) => `${v >= 0 ? '+' : '−'}${formatNumber(Math.abs(v), 3)}`

  return (
    <ChartCard
      title={`Why this forecast: ${sensor.label} at ${formatTime(data.target_time, true)}`}
      subtitle={`${horizonLabel(horizon)} forecast, from the recent level (median of the last 3 readings)`}
      info="Bars to the right raise the forecast and bars to the left lower it. Red and blue show direction only, not good or bad."
      columns={['Input', `Effect (${sensor.unit})`]}
      rows={[
        ['Recent level', formatNumber(data.recent_level, 3)],
        ...items.map((i) => [rowName(i), signed(i.contribution)]),
        ['Forecast', formatNumber(data.prediction, 3)],
      ]}
    >
      <div className="grid gap-4 lg:grid-cols-[180px_minmax(0,1fr)]">
        <div className="flex gap-6 lg:flex-col">
          <Stat label="Recent level" value={formatNumber(data.recent_level, 3)} unit={sensor.unit} />
          <Stat label="Forecast" value={formatNumber(data.prediction, 3)} unit={sensor.unit} />
        </div>
        <div className="min-w-0 space-y-1">
          {items.map((item, idx) => {
            const v = item.contribution
            const width = (Math.abs(v) / biggest) * 50
            return (
              <div key={idx} className="flex items-center gap-2 text-xs">
                <span className="w-32 shrink-0 truncate text-ink2 sm:w-56" title={rowName(item)}>{rowName(item)}</span>
                <span className="relative h-2.5 flex-1">
                  <span className="absolute inset-y-0 left-1/2 w-px bg-[var(--axis)]" />
                  <span
                    className="absolute inset-y-0 rounded-sm"
                    style={{
                      background: v >= 0 ? 'var(--up)' : 'var(--down)',
                      width: `${width}%`,
                      left: v >= 0 ? '50%' : `${50 - width}%`,
                    }}
                  />
                </span>
                <span className="tnum w-14 text-right">{signed(v)}</span>
              </div>
            )
          })}
        </div>
      </div>
    </ChartCard>
  )
}
