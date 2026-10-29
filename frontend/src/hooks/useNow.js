import { useEffect, useState } from 'react'

/** The current time in ms, refreshed every `intervalMs`, so ages and staleness update on their own. */
export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])

  return now
}
