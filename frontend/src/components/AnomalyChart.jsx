import { useMemo } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { formatNumber, formatTime, usePoll } from '../api'
import ChartCard, { AXIS, ChartTooltip, formatTick, gapAreas, LegendKey, LegendSwatch, niceAxis, timeAxis } from './ChartCard'
import { StatusLabel } from './SensorCards'

const STATUS_NOTE = {
  warming_up: 'Needs 3 days of readings before scoring starts.',
  flatline: 'The reading has not changed for a whole window, which usually means a stuck sensor.',
  undetermined: 'Over half the windows score the same, so the data gives no usable threshold.',
  insufficient_data: 'Too many readings are missing from the latest window to score it.',
  stale: 'No reading in the last hour.',
}

export default function AnomalyChart({ sensor, config }) {
  const { data, error } = usePoll(`/api/anomalies/${sensor.key}`)

  const values = useMemo(() => data?.value_t.map((t, i) => ({ t: Date.parse(t), y: data.value_y[i] })) ?? [], [data])
  const scores = useMemo(() => data?.times.map((t, i) => ({ t: Date.parse(t), s: data.scores[i] })) ?? [], [data])
  const ranges = useMemo(() => data?.flagged_ranges.map((r) => ({ a: Date.parse(r.start), b: Date.parse(r.end) })) ?? [], [data])

  if (error && !data) return <section className="card p-4 text-sm text-ink2">{error}</section>
  if (!data || !values.length) return null
  const domain = [values[0].t, values[values.length - 1].t]
  const axis = timeAxis(domain)
  const hours = data.window_hours
  const gaps = gapAreas(data.gaps)
  const estimated = data.value_estimated.filter(Boolean).length

  return (
    <>
      <ChartCard
        title={`${sensor.label}: last 3 days`}
        subtitle={STATUS_NOTE[data.status]}
        info={`Shaded spans are ${hours} h windows that look unlike the rest of the 3 days. The whole window is shaded because s-IDK scores a window, not a single reading. Gaps of up to 30 minutes are joined with a straight line (${estimated} estimated points here); longer outages are left empty.`}
        legend={<>
          <LegendKey color="var(--series-1)" label="Measured" />
          <LegendSwatch color="var(--flag-wash)" label={`Flagged windows (${ranges.length})`} />
          {gaps.length > 0 && <LegendSwatch color="var(--gap-wash)" label={`No data (${gaps.length})`} />}
          {data.spikes.length > 0 && <LegendKey color="var(--muted)" label={`Single-reading glitches (${data.spikes.length})`} />}
          <StatusLabel status={data.status} />
        </>}
        columns={['Type', 'From', 'To', 'Reading']}
        rows={[
          ...ranges.map((r) => ['Flagged window', formatTime(r.a, true), formatTime(r.b, true), '—']),
          ...data.spikes.map((s) => ['Glitch', formatTime(s.t, true), '—', `${formatNumber(s.y, 2)} ${sensor.unit}`]),
          ...gaps.map((g) => ['No data', formatTime(g.a, true), formatTime(g.b, true), '—']),
        ]}
      >
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={values} syncId="anomaly" margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="t" type="number" scale="time" domain={domain} {...axis} {...AXIS} />
              <YAxis {...niceAxis(values.map((p) => p.y))} width={48} axisLine={false} tickFormatter={formatTick} {...AXIS} />
              <Tooltip content={<ChartTooltip format={(t) => formatTime(t, true)} unit={sensor.unit} />} />
              {ranges.map((r) => <ReferenceArea key={r.a} x1={r.a} x2={r.b} fill="var(--flag-wash)" fillOpacity={1} stroke="none" />)}
              {gaps.map((g) => <ReferenceArea key={g.a} x1={g.a} x2={g.b} fill="var(--gap-wash)" fillOpacity={1} stroke="none" />)}
              {data.spikes.map((s) => <ReferenceLine key={s.t} x={Date.parse(s.t)} stroke="var(--muted)" />)}
              <Line name="Measured" dataKey="y" stroke="var(--series-1)" strokeWidth={1.75} dot={false} isAnimationActive={false} connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        {data.spikes.length > 0 && (
          <p className="mt-2 text-xs text-ink2">
            Glitches are left out of the line, the forecast and s-IDK: {data.spikes.map((s) => `${formatTime(s.t, true)} (${formatNumber(s.y, 2)} ${sensor.unit})`).join(', ')}.
          </p>
        )}
      </ChartCard>

      {scores.length > 0 && (
        <ChartCard
          title="s-IDK similarity score"
          subtitle={`Window ${config.idk_width} steps (${hours} h), psi ${config.idk_psi}`}
          info="Each point scores the window ending at that time against the other windows in the last 3 days. Lower means less alike. A window is flagged when its score falls below the threshold."
          legend={<>
            <LegendKey color="var(--series-1)" label="Similarity" />
            <LegendKey color="var(--up)" label={data.threshold == null ? 'No threshold' : `Threshold ${formatNumber(data.threshold, 3)}`} />
          </>}
          columns={['Window end', 'Similarity']}
          rows={scores.slice(-288).reverse().map((p) => [formatTime(p.t, true), formatNumber(p.s, 4)])}
        >
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={scores} syncId="anomaly" margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="t" type="number" scale="time" domain={domain} {...axis} {...AXIS} />
                <YAxis {...niceAxis([data.threshold, ...scores.map((p) => p.s)])} width={48} axisLine={false} tickFormatter={formatTick} {...AXIS} />
                <Tooltip content={<ChartTooltip format={(t) => formatTime(t, true)} />} />
                {data.threshold != null && <ReferenceLine y={data.threshold} stroke="var(--up)" strokeWidth={1.5} />}
                <Line name="Similarity" dataKey="s" stroke="var(--series-1)" strokeWidth={1.75} dot={false} isAnimationActive={false} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
      )}
    </>
  )
}
