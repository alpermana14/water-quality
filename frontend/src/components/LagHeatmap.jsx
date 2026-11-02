import { useMemo } from 'react'
import { formatNumber, horizonLabel, lagLabel } from '../api'
import ChartCard from './ChartCard'

const BINS = 7

export default function LagHeatmap({ sensor, data, input, labelOf }) {
  const grid = data.input_sensors[input].heatmap_hour
  const max = useMemo(() => Math.max(...grid.flat(), 1e-12), [grid])
  const bin = (v) => Math.min(BINS - 1, Math.floor((Math.sqrt(v / max)) * BINS))
  const shown = data.horizons.map((h, i) => ({ h, row: grid[i] })).filter(({ h }) => h % 3 === 0)

  return (
    <ChartCard
      title={`How reliance shifts with look-ahead: ${labelOf(input)}`}
      subtitle={`Influence on the ${sensor.label} forecast, every 15 minutes of look-ahead`}
      columns={['Look-ahead', ...data.lag_hours.map((h) => `${h} h`)]}
      rows={shown.map(({ h, row }) => [horizonLabel(h), ...row.map((v) => formatNumber(v, 4))])}
    >
      <div className="overflow-x-auto">
        <div className="min-w-[440px]">
          {shown.map(({ h, row }) => (
            <div key={h} className="flex items-center gap-2">
              <span className="tnum w-20 shrink-0 text-right text-[11px] text-ink2">{horizonLabel(h)}</span>
              <div className="grid flex-1 gap-px" style={{ gridTemplateColumns: `repeat(${row.length}, 1fr)` }}>
                {row.map((v, i) => (
                  <div
                    key={i} className="h-3.5"
                    style={{ background: `var(--seq-${bin(v)})` }}
                    title={`${horizonLabel(h)}, ${lagLabel(i)}: ${formatNumber(v, 4)} ${sensor.unit}`}
                  />
                ))}
              </div>
            </div>
          ))}
          <div className="mt-1 flex gap-2">
            <span className="w-20 shrink-0" />
            <div className="flex flex-1 justify-between text-[11px] text-ink2">
              <span>Latest hour</span><span>12 h ago</span><span>24 h ago</span>
            </div>
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-1.5 text-[11px] text-ink2">
        Less
        {Array.from({ length: BINS }, (_, i) => (
          <span key={i} className="h-2.5 w-4" style={{ background: `var(--seq-${i})` }} />
        ))}
        More
      </div>
    </ChartCard>
  )
}
