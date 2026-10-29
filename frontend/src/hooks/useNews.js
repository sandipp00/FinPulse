import { useEffect, useState } from 'react'
import { getCalendar, getNews } from '../api/finpulse'

function useLoad(load) {
  const [state, setState] = useState({ data: null, loading: true, error: '', loadedAt: null })

  useEffect(() => {
    let cancelled = false
    load()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: '', loadedAt: Date.now() })
      })
      .catch((err) => {
        if (!cancelled) setState({ data: null, loading: false, error: err.message || 'Unable to load.', loadedAt: Date.now() })
      })
    return () => {
      cancelled = true
    }
  }, [load])

  return state
}

/** Headlines from every news source, with per-source status (/api/news). */
export function useNews() {
  return useLoad(getNews)
}

/** Scheduled releases and policy meetings (/api/calendar). */
export function useCalendar() {
  return useLoad(getCalendar)
}
