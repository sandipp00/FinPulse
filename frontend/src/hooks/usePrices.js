import { useEffect, useState } from 'react'
import { getPrices } from '../api/finpulse'

/** Stored price history for one symbol from /api/prices. */
export function usePrices(symbol, limit = 2000) {
  // Keep the result together with the symbol it belongs to, so "loading" can
  // be derived instead of set synchronously inside the effect.
  const [result, setResult] = useState({ symbol: null, prices: [], error: '' })

  useEffect(() => {
    let cancelled = false

    getPrices(symbol, limit)
      .then((response) => {
        if (cancelled) return
        setResult({
          symbol,
          prices: Array.isArray(response.prices) ? response.prices : [],
          error: '',
        })
      })
      .catch((err) => {
        if (cancelled) return
        setResult({
          symbol,
          prices: [],
          error: err.message || 'Unable to load historical prices.',
        })
      })

    return () => {
      cancelled = true
    }
  }, [symbol, limit])

  const loading = result.symbol !== symbol
  return {
    prices: loading ? [] : result.prices,
    loading,
    error: loading ? '' : result.error,
  }
}
