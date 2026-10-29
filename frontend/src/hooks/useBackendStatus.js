import { useEffect, useState } from 'react'
import { getHealth, getLiveStatus } from '../api/finpulse'

const POLL_MS = 30_000

/**
 * The backend's own view of itself, polled from /api/health (database) and
 * /api/live/status (exchange feed). Each check fails on its own, so a broken
 * feed does not hide a working database or the other way round.
 */
export function useBackendStatus() {
  const [state, setState] = useState({
    health: null,
    healthError: '',
    live: null,
    liveError: '',
    checkedAt: null,
    loading: true,
  })

  useEffect(() => {
    let cancelled = false

    const poll = async () => {
      const [health, live] = await Promise.allSettled([getHealth(), getLiveStatus()])
      if (cancelled) return
      setState({
        health: health.status === 'fulfilled' ? health.value : null,
        healthError: health.status === 'rejected' ? health.reason?.message || 'Health check failed' : '',
        live: live.status === 'fulfilled' ? live.value : null,
        liveError: live.status === 'rejected' ? live.reason?.message || 'Feed status unavailable' : '',
        checkedAt: Date.now(),
        loading: false,
      })
    }

    poll()
    const timer = setInterval(poll, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  return state
}
