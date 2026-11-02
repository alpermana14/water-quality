import { useMemo, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { digitsFor, formatNumber, formatTime, horizonLabel, usePoll } from '../api'
import ChartCard, {
  AXIS, breakLongGaps, ChartTooltip, formatTick, HORIZONS, LegendKey, niceAxis, ReliabilityChip, Segmented, Stat, timeAxis,
} from './ChartCard'

const signedText = (v, digits) => `${v >= 0 ? '+' : '−'}${formatNumber(Math.abs(v), digits)}`

function verdict(s, unit, label, digits) {
  const typical = `At ${label}, forecasts were typically off by ${formatNumber(s.mae, digits)} ${unit}`
  if (s.skill == null) return `${typical}.`
  const percent = Math.abs(Math.round(s.skill * 100))
  if (percent < 5) return `${typical}, about the same as assuming the latest reading stays unchanged.`
  if (s.skill > 0) return `${typical}, ${percent}% closer than assuming the latest reading stays unchanged.`
  return `${typical}, ${percent}% further off than assuming the latest reading stays unchanged. Do not rely on this look-ahead yet.`
}

export default function ForecastValidation({ sensor }) {
  const [horizon, setHorizon] = useState(12)
  const { data, error } = usePoll(`/api/forecast/${sensor.key}/validation?horizon=${horizon}`)

  const points = useMemo(() => {
    if (!data) return []
    const expand = ({ t, forecast, actual, persistence }, source) => t.map((time, i) => ({
      t: Date.parse(time), forecast: forecast[i], actual: actual[i], persistence: persistence[i], source,
      error: +(forecast[i] - actual[i]).toFixed(4),
    }))
    return breakLongGaps([...expand(data.backtest, 'Backtest'), ...expand(data.live, 'Live')])
  }, [data])

  if (error && !data) return <section className="card p-4 text-sm text-ink2">{error}</section>
  if (!data) return null

  const label = horizonLabel(data.horizon)
  const s = data.summary.combined
  if (!s) {
    return (
      <section className="card p-4">
        <h2 className="text-sm font-semibold">Forecast vs actual</h2>
        <p className="mt-1 text-sm text-ink2">No measured results to compare yet. They appear after the next retrain.</p>
      </section>
    )
  }

  const digits = digitsFor(s.mae)
  const firstLive = data.live.t.length ? Date.parse(data.live.t[0]) : null
  const domain = [points[0].t, points[points.length - 1].t]
  const axis = timeAxis(domain)
  const { live, backtest } = data.summary

  return (
    <ChartCard
      title="Forecast vs actual"
      subtitle={[
        backtest && `${backtest.n} backtest forecasts`,
        live ? `${live.n} live` : 'no live results at this look-ahead yet',
      ].filter(Boolean).join(' · ')}
      info="Every point compares a past forecast with the reading later measured at that time. None of those readings were used to train the model that made the forecast. Single-reading glitches are left out of the true values."
      columns={['Time', 'Source', `True value (${sensor.unit})`, 'Forecast', 'Error']}
      rows={points.filter((p) => !p.gapBreak).reverse().map((p) => [
        formatTime(p.t, true), p.source, formatNumber(p.actual, 3), formatNumber(p.forecast, 3), signedText(p.error, 3),
      ])}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Segmented label="Look-ahead" options={HORIZONS} value={horizon} onChange={setHorizon} />
        <ReliabilityChip skill={s.skill} />
      </div>

      <p className="mt-3 text-sm text-ink">{verdict(s, sensor.unit, label, digits)}</p>

      <div className="mt-3 grid grid-cols-2 gap-3 border-y border-line py-3 md:grid-cols-4">
        <Stat label="Typical error" value={formatNumber(s.mae, digits)} unit={sensor.unit} note={`${formatNumber((s.mae / Math.abs(s.mean_actual)) * 100, 1)}% of average reading`} />
        <Stat label="Largest error" value={formatNumber(s.max_error, digits)} unit={sensor.unit} note={`across ${s.n} forecasts`} />
        <Stat label="Average lean" value={signedText(s.bias, digits)} unit={sensor.unit} note={s.bias >= 0 ? 'forecasts run high' : 'forecasts run low'} />
        <Stat label="Baseline error" value={formatNumber(s.persistence_mae, digits)} unit={sensor.unit} note="if reading stays the same" />
      </div>

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink2">
        <LegendKey color="var(--series-1)" label="True value" />
        <LegendKey color="var(--series-2)" label={`Forecast made ${label.slice(1)} earlier`} />
      </div>
      <div className="mt-2 h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} syncId="validation" margin={{ top: 16, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="t" type="number" scale="time" domain={domain} {...axis} {...AXIS} />
            <YAxis {...niceAxis(points.flatMap((p) => [p.actual, p.forecast]))} width={48} axisLine={false} tickFormatter={formatTick} {...AXIS} />
            <Tooltip content={<ChartTooltip format={(t) => formatTime(t, true)} unit={sensor.unit} />} />
            {firstLive && <ReferenceLine x={firstLive} stroke="var(--muted)" label={{ value: 'Live', position: 'top', fill: 'var(--ink-2)', fontSize: 11 }} />}
            <Line name="True value" dataKey="actual" stroke="var(--series-1)" strokeWidth={1.75} dot={false} isAnimationActive={false} />
            <Line name="Forecast" dataKey="forecast" stroke="var(--series-2)" strokeWidth={1.75} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <h3 className="mt-4 text-xs font-medium">Error (forecast minus true value)</h3>
      <p className="text-xs text-ink2">Thin lines mark the typical error, ±{formatNumber(s.mae, digits)} {sensor.unit}</p>
      <div className="mt-1 h-36">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} syncId="validation" margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="t" type="number" scale="time" domain={domain} {...axis} {...AXIS} />
            <YAxis {...niceAxis([0, s.mae, -s.mae, ...points.map((p) => p.error)])} width={48} axisLine={false} tickFormatter={formatTick} {...AXIS} />
            <Tooltip content={<ChartTooltip format={(t) => formatTime(t, true)} unit={sensor.unit} />} />
            <ReferenceLine y={0} stroke="var(--muted)" strokeWidth={1.5} />
            <ReferenceLine y={s.mae} stroke="var(--axis)" />
            <ReferenceLine y={-s.mae} stroke="var(--axis)" />
            {firstLive && <ReferenceLine x={firstLive} stroke="var(--muted)" />}
            <Line name="Error" dataKey="error" stroke="var(--series-2)" strokeWidth={1.75} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  )
}
