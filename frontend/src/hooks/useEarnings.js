import { useEffect, useState } from 'react'
import { getEarnings } from '../api/finpulse'

/** /api/earnings for every followed stock, or one stock's: { data, error, loading }. */
export function useEarnings(symbol) {
  const [state, setState] = useState({ key: null, data: null, error: '' })
  const key = symbol ?? '*'

  useEffect(() => {
    let cancelled = false
    getEarnings(symbol)
      .then((data) => { if (!cancelled) setState({ key, data, error: '' }) })
      .catch((error) => { if (!cancelled) setState({ key, data: null, error: error.message || 'Unavailable' }) })
    return () => {
      cancelled = true
    }
  }, [symbol, key])

  const current = state.key === key
  return { data: current ? state.data : null, error: current ? state.error : '', loading: !current }
}
