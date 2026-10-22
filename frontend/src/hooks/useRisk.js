import { useEffect, useState } from 'react'
import { getRisk } from '../api/finpulse'

const FRESH_MS = 60_000

// One request shared by every page that needs the risk report (Risk monitor,
// Research, ...), so moving between them does not refetch. A failed request is
// not kept, so the next visit tries again.
let shared = null

function loadRisk() {
  if (!shared || Date.now() - shared.startedAt > FRESH_MS) {
    const entry = { startedAt: Date.now(), promise: null }
    entry.promise = getRisk().catch((error) => {
      if (shared === entry) shared = null
      throw error
    })
    shared = entry
  }
  return shared.promise
}

/** The /api/risk report: { data, loading, error }. */
export function useRisk() {
  const [state, setState] = useState({ data: null, error: '', done: false })

  useEffect(() => {
    let cancelled = false

    loadRisk()
      .then((data) => {
        if (!cancelled) setState({ data, error: '', done: true })
      })
      .catch((error) => {
        if (!cancelled) setState({ data: null, error: error.message || 'Unable to load risk figures.', done: true })
      })

    return () => {
      cancelled = true
    }
  }, [])

  return { data: state.data, error: state.error, loading: !state.done }
}
