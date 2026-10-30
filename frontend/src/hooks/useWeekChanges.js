import { useEffect, useState } from 'react'
import { getWeekChanges } from '../api/finpulse'

const REFRESH_MS = 5 * 60 * 1000

/** symbol -> 7-day change for these symbols (from each one's daily bars), refreshed every 5 minutes. */
export function useWeekChanges(symbols) {
  const key = [...symbols].sort().join(',')
  const [changes, setChanges] = useState({})

  useEffect(() => {
    if (!key) return undefined
    let cancelled = false
    let timer = null
    const load = () => {
      getWeekChanges(key.split(','))
        .then((data) => !cancelled && setChanges(data.changes))
        .catch(() => {}) // keep what is shown; the next refresh tries again
        .finally(() => {
          if (!cancelled) timer = setTimeout(load, REFRESH_MS)
        })
    }
    load()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [key])

  return changes
}
