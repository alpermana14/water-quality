import { useEffect, useState } from 'react'
import { setDisplayZone, usePoll } from './api'
import Sidebar, { VIEWS } from './components/Sidebar'
import StatusBar, { Notices } from './components/StatusBar'
import SensorCards from './components/SensorCards'
import ForecastChart from './components/ForecastChart'
import AnomalyChart from './components/AnomalyChart'
import EpisodePanel from './components/EpisodePanel'
import LagInfluence from './components/LagInfluence'

export default function App() {
  const { data: status, error } = usePoll('/api/status')
  const { data: episodes, reload: reloadEpisodes } = usePoll('/api/episodes')
  const [sensor, setSensor] = useState(null)
  const [view, setView] = useState('forecast')

  if (status) setDisplayZone(status.display_timezone)
  useEffect(() => {
    if (!sensor && status?.sensors?.length) setSensor(status.sensors[0].key)
  }, [status, sensor])

  const selected = status?.sensors?.find((s) => s.key === sensor)
  const title = VIEWS.find((v) => v.key === view).label

  return (
    <div className="flex min-h-screen">
      <Sidebar view={view} onView={setView} status={status} />
      <div className="min-w-0 flex-1">
        <StatusBar title={title} status={status} episodes={episodes} view={view} onView={setView} />
        <main className="mx-auto max-w-[1400px] space-y-4 p-4 lg:p-6">
          <Notices status={status} error={error} />
          {status?.sensors?.length > 0 && (
            <SensorCards sensors={status.sensors} selected={sensor} onSelect={setSensor} />
          )}
          {selected && view === 'forecast' && <ForecastChart sensor={selected} model={status.model} />}
          {selected && view === 'anomalies' && <AnomalyChart sensor={selected} config={status.config} />}
          {selected && view === 'anomalies' && (
            <EpisodePanel sensors={status.sensors} episodes={episodes} reload={reloadEpisodes} />
          )}
          {selected && view === 'influence' && <LagInfluence sensor={selected} sensors={status.sensors} />}
        </main>
      </div>
    </div>
  )
}
