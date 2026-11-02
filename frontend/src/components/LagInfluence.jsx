import { useMemo, useState } from 'react'
import { usePoll } from '../api'
import { HORIZONS, Segmented } from './ChartCard'
import LagProfile from './LagProfile'
import LagHeatmap from './LagHeatmap'
import ForecastExplain from './ForecastExplain'

const RESOLUTION = [['hour', '1 h groups'], ['step', '5 min lags']]

function Control({ label, children }) {
  return (
    <div className="flex min-w-0 max-w-full flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink2">
      {label}
      {children}
    </div>
  )
}

export default function LagInfluence({ sensor, sensors }) {
  const { data, error } = usePoll(`/api/explain/${sensor.key}/lags`)
  const [horizon, setHorizon] = useState(36)
  const [picked, setPicked] = useState(null)
  const [resolution, setResolution] = useState('hour')

  const inputs = useMemo(() => (data ? Object.keys(data.input_sensors) : []), [data])
  const input = picked && inputs.includes(picked) ? picked : sensor.key
  const labelOf = (key) => sensors.find((s) => s.key === key)?.label || key

  if (error && !data) return <section className="card p-4 text-sm text-ink2">{error}</section>
  if (!data) return null

  return (
    <>
      <div className="card flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5">
        <Control label="Look-ahead">
          <Segmented label="Look-ahead" options={HORIZONS} value={horizon} onChange={setHorizon} />
        </Control>
        <Control label="Input sensor">
          <select className="control" value={input} onChange={(e) => setPicked(e.target.value)}>
            {inputs.map((k) => <option key={k} value={k}>{labelOf(k)}</option>)}
          </select>
        </Control>
        <Control label="Lag detail">
          <Segmented label="Lag detail" options={RESOLUTION} value={resolution} onChange={setResolution} />
        </Control>
      </div>

      <p className="text-xs text-ink2">
        Built-in LightGBM TreeSHAP contributions. They show how the model uses its inputs, not physical cause, and
        neighbouring lags share credit arbitrarily, so read the overall shape rather than a single lag.
      </p>

      <ForecastExplain sensor={sensor} horizon={horizon} labelOf={labelOf} />
      <div className="grid gap-4 xl:grid-cols-2">
        <LagProfile sensor={sensor} data={data} input={input} horizon={horizon} fineLags={resolution === 'step'} labelOf={labelOf} />
        <LagHeatmap sensor={sensor} data={data} input={input} labelOf={labelOf} />
      </div>
    </>
  )
}
