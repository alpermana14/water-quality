import { useMemo } from 'react'
import {
  Area, CartesianGrid, ComposedChart, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { digitsFor, formatNumber, formatTime, horizonLabel, usePoll } from '../api'
import ChartCard, {
  AXIS, ChartTooltip, formatTick, gapAreas, LegendKey, LegendSwatch, niceAxis, ReliabilityChip, timeAxis,
} from './ChartCard'
import ForecastValidation from './ForecastValidation'

const OUTLOOK = [[12, '+1 h'], [36, '+3 h']]

function Outlook({ sensor, data, backtest }) {
  const latest = [...data.actual_y].reverse().find((y) => y != null)
  const digits = digitsFor(latest)
  return (
    <section className="card">
      <h2 className="border-b border-line px-4 py-3 text-sm font-semibold">Outlook</h2>
      <div className="divide-y divide-[var(--line)]">
        <div className="px-4 py-3">
          <div className="text-xs text-ink2">Now</div>
          <div className="text-xl font-semibold">{formatNumber(latest, digits)} <span className="text-xs font-normal text-ink2">{sensor.unit}</span></div>
        </div>
        {OUTLOOK.map(([h, label]) => {
          const value = data.forecast_y[h - 1]
          const row = backtest[h - 1]
          return (
            <div key={h} className="px-4 py-3">
              <div className="text-xs text-ink2">{label}</div>
              <div className="text-xl font-semibold">
                {formatNumber(value, digits)}{' '}
                <span className="text-xs font-normal text-ink2">± {formatNumber(row?.mae, digitsFor(row?.mae))} {sensor.unit}</span>
              </div>
              <div className="mt-1"><ReliabilityChip skill={row?.skill} /></div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

export default function ForecastChart({ sensor, model }) {
  const { data, error } = usePoll(`/api/forecast/${sensor.key}`)
  const { data: skill } = usePoll(`/api/forecast/${sensor.key}/skill`)
  const backtest = useMemo(() => skill?.backtest ?? [], [skill])

  const points = useMemo(() => {
    if (!data) return []
    const actual = data.actual_t.map((t, i) => ({
      t: Date.parse(t), actual: data.actual_y[i], estimated: data.actual_estimated[i],
    }))
    const future = data.forecast_t.map((t, i) => {
      const y = data.forecast_y[i]
      const mae = backtest[i]?.mae
      return { t: Date.parse(t), forecast: y, band: mae == null ? null : [y - mae, y + mae] }
    })
    if (future.length) {
      // Start the forecast line and its range from the last measured point, so the two meet at Now.
      const last = actual.findLast((p) => p.actual != null)
      if (last) Object.assign(last, { forecast: last.actual, band: [last.actual, last.actual], join: true })
    }
    return [...actual, ...future]
  }, [data, backtest])

  if (error && !data) return <section className="card p-4 text-sm text-ink2">{error}</section>
  if (!data || !points.length) return null
  const origin = data.origin ? Date.parse(data.origin) : null
  const domain = [points[0].t, points[points.length - 1].t]
  const hasForecast = data.forecast_y.length > 0
  const gaps = gapAreas(data.gaps)

  return (
    <>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_260px]">
        <ChartCard
          title={`${sensor.label}: last 24 h and next 3 h`}
          subtitle={data.unavailable_reason}
          info="Each of the 36 future points has its own LightGBM model, using the last 24 h of all sensors. The shaded range is the typical backtest error at that look-ahead. Gaps of up to 30 minutes are joined with a straight line and marked as estimated in the table; longer outages are left empty."
          columns={['Time', 'Measured', 'Forecast']}
          rows={points.map((p) => [
            formatTime(p.t, true),
            `${formatNumber(p.actual, 3)}${p.estimated ? ' (estimated)' : ''}`,
            p.join ? '—' : formatNumber(p.forecast, 3),
          ])}
          legend={<>
            <LegendKey color="var(--series-1)" label="Measured" />
            {hasForecast && <LegendKey color="var(--series-2)" label="Forecast" />}
            {hasForecast && <LegendSwatch color="var(--band)" label="Typical error" />}
            {gaps.length > 0 && <LegendSwatch color="var(--gap-wash)" label="No data" />}
          </>}
        >
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={points} margin={{ top: 16, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="t" type="number" scale="time" domain={domain} {...timeAxis(domain)} {...AXIS} />
                <YAxis {...niceAxis(points.flatMap((p) => [p.actual, p.forecast, ...(p.band ?? [])]))} width={48} axisLine={false} tickFormatter={formatTick} {...AXIS} />
                <Tooltip content={<ChartTooltip format={(t) => formatTime(t, true)} unit={sensor.unit} />} />
                {gaps.map((g) => <ReferenceArea key={g.a} x1={g.a} x2={g.b} fill="var(--gap-wash)" fillOpacity={1} stroke="none" />)}
                {origin && (
                  <ReferenceLine x={origin} stroke="var(--muted)" label={{ value: 'Now', position: 'top', fill: 'var(--ink-2)', fontSize: 11 }} />
                )}
                <Area dataKey="band" stroke="none" fill="var(--band)" fillOpacity={1} isAnimationActive={false} connectNulls={false} activeDot={false} />
                <Line name="Measured" dataKey="actual" stroke="var(--series-1)" strokeWidth={1.75} dot={false} isAnimationActive={false} connectNulls={false} />
                <Line name="Forecast" dataKey="forecast" stroke="var(--series-2)" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
        {hasForecast && <Outlook sensor={sensor} data={data} backtest={backtest} />}
      </div>

      {backtest.length > 0 && <ForecastValidation sensor={sensor} />}

      {backtest.length > 0 && (
        <ChartCard
          title="Error by look-ahead"
          subtitle={`Backtest on the last ${formatNumber(model?.holdout_hours, 0)} hours, kept out of training`}
          info="Persistence is the simple baseline of assuming the latest reading stays the same. The model only adds value where its line sits below persistence."
          columns={['Look-ahead', `Model MAE (${sensor.unit})`, `Persistence MAE (${sensor.unit})`, 'Improvement']}
          rows={backtest.map((r) => [
            horizonLabel(r.horizon), formatNumber(r.mae, 4), formatNumber(r.persistence_mae, 4),
            r.skill == null ? '—' : `${Math.round(r.skill * 100)}%`,
          ])}
          legend={<>
            <LegendKey color="var(--series-2)" label="Model" />
            <LegendKey color="var(--series-1)" label="Persistence" />
          </>}
        >
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={backtest} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="horizon" type="number" domain={[1, 36]} ticks={[6, 12, 18, 24, 30, 36]} tickFormatter={horizonLabel} {...AXIS} />
                <YAxis {...niceAxis([0, ...backtest.flatMap((r) => [r.mae, r.persistence_mae])])} width={48} axisLine={false} tickFormatter={formatTick} {...AXIS} />
                <Tooltip content={<ChartTooltip format={horizonLabel} unit={sensor.unit} />} />
                <Line name="Model" dataKey={(r) => r.mae == null ? null : +r.mae.toFixed(4)} stroke="var(--series-2)" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line name="Persistence" dataKey={(r) => r.persistence_mae == null ? null : +r.persistence_mae.toFixed(4)} stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          {skill?.live?.length > 0 && (
            <p className="mt-2 text-xs text-ink2">
              Live error, last 24 h: {skill.live.map((l) => `${l.label} ${formatNumber(l.mae, 3)} ${sensor.unit} (${l.n} forecasts)`).join(' · ')}
            </p>
          )}
        </ChartCard>
      )}
    </>
  )
}
