import { useCallback, useEffect, useRef, useState } from 'react'

const POLL_MS = 60000
// Empty when the backend serves the frontend itself; set at build time when they are deployed apart.
const API_URL = import.meta.env.VITE_API_URL || ''

export async function getJson(path, options) {
  const res = await fetch(`${API_URL}${path}`, options)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const error = new Error(body.detail || `Request failed (${res.status})`)
    error.status = res.status
    throw error
  }
  return res.json()
}

/* Keeps the previous data on screen while refetching, so polling never flashes a blank chart. */
export function usePoll(path) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const latestPath = useRef(path)
  latestPath.current = path

  const load = useCallback(async () => {
    if (!path) return
    try {
      const body = await getJson(path)
      if (latestPath.current === path) {
        setData(body)
        setError(null)
      }
    } catch (err) {
      if (latestPath.current === path) setError(err.message)
    }
  }, [path])

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [load])

  return { data, error, reload: load }
}

let displayZone = 'UTC'
export const setDisplayZone = (zone) => { displayZone = zone || 'UTC' }

export function formatTime(value, withDate = false) {
  if (value == null) return '—'
  const options = withDate
    ? { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }
    : { hour: '2-digit', minute: '2-digit', hour12: false }
  return new Intl.DateTimeFormat('en-GB', { ...options, timeZone: displayZone }).format(new Date(value))
}

export function formatDate(value) {
  return new Intl.DateTimeFormat('en-GB', { month: 'short', day: 'numeric', timeZone: displayZone }).format(new Date(value))
}

export function zoneLabel() {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: displayZone, timeZoneName: 'short' }).formatToParts(new Date())
  return parts.find((p) => p.type === 'timeZoneName')?.value ?? displayZone
}

export function formatNumber(value, digits = 2) {
  if (value == null) return '—'
  return Number(value).toLocaleString('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: 0 })
}

/* Enough digits to show the size of an error, whatever the sensor's scale. */
export function digitsFor(value) {
  if (!value) return 2
  return Math.min(4, Math.max(1, 2 - Math.floor(Math.log10(Math.abs(value)))))
}

export function lagLabel(hour) {
  return hour === 0 ? 'last hour' : `${hour}–${hour + 1} h ago`
}

export function horizonLabel(steps) {
  const minutes = steps * 5
  if (minutes < 60) return `+${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m ? `+${h} h ${m} min` : `+${h} h`
}

/* How a look-ahead compares with assuming the latest reading stays the same. */
export function reliability(skill) {
  if (skill == null) return { key: 'unknown', label: 'Not enough results' }
  if (skill >= 0.05) return { key: 'good', label: 'Beats baseline' }
  if (skill > -0.05) return { key: 'neutral', label: 'Same as baseline' }
  return { key: 'poor', label: 'Worse than baseline' }
}
