import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatNumber, horizonLabel, lagLabel } from '../api'
import ChartCard, { AXIS, formatTick, niceAxis } from './ChartCard'

function BarTip({ active, payload, unit }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="card px-2 py-1.5 text-xs shadow-sm">
      <div className="text-ink2">{p.label}</div>
      <div className="tnum">{formatNumber(p.value, 4)} {unit}</div>
    </div>
  )
}

function ShareRow({ label, share }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 shrink-0 truncate text-ink2">{label}</span>
      <span className="h-1.5 flex-1 rounded-sm bg-[var(--line)]">
        <span className="block h-1.5 rounded-sm" style={{ width: `${share * 100}%`, background: 'var(--series-1)' }} />
      </span>
      <span className="tnum w-9 text-right">{Math.round(share * 100)}%</span>
    </div>
  )
}

export default function LagProfile({ sensor, data, input, horizon, fineLags, labelOf }) {
  const source = data.input_sensors[input]
  const shares = Object.entries(data.input_sensors)
    .map(([key, v]) => ({ key, share: v.share }))
    .sort((a, b) => b.share - a.share)

  const bars = fineLags
    ? source.by_lag.map((value, i) => ({ x: i, value, label: `${i * 5} min ago` }))
    : source.heatmap_hour[horizon - 1].map((value, i) => ({ x: i, value, label: lagLabel(i) }))

  return (
    <ChartCard
      title={`How far back the forecast looks: ${labelOf(input)}`}
      subtitle={fineLags ? 'Each 5-minute lag, averaged over all look-aheads' : `${horizonLabel(horizon)} ${sensor.label} forecast, average over the backtest`}
      columns={['Reading age', `Mean influence (${sensor.unit})`]}
      rows={bars.map((b) => [b.label, formatNumber(b.value, 5)])}
    >
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={bars} margin={{ top: 8, right: 12, left: 0, bottom: 14 }} barCategoryGap={fineLags ? 0 : 2}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis
              dataKey="x" interval={fineLags ? 35 : 2} {...AXIS}
              tickFormatter={(x) => (fineLags ? `${x / 12} h` : `${x} h`)}
              label={{ value: 'Age of reading', position: 'insideBottom', offset: -8, fill: 'var(--muted)', fontSize: 11 }}
            />
            <YAxis {...niceAxis([0, ...bars.map((b) => b.value)])} width={48} axisLine={false} tickFormatter={formatTick} {...AXIS} />
            <Tooltip content={<BarTip unit={sensor.unit} />} cursor={{ fill: 'var(--line)', opacity: 0.5 }} />
            <Bar dataKey="value" fill="var(--series-1)" radius={fineLags ? 0 : [2, 2, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <h3 className="mt-3 text-xs font-medium">Share of influence by input</h3>
      <div className="mt-2 space-y-1.5">
        {shares.map((s) => <ShareRow key={s.key} label={labelOf(s.key)} share={s.share} />)}
        <ShareRow label="Time of day" share={data.clock_share} />
      </div>
    </ChartCard>
  )
}
