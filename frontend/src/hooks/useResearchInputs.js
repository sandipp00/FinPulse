import { useEffect, useState } from 'react'
import { getBacktest, getSignals } from '../api/finpulse'

const settledValue = (result) => (result.status === 'fulfilled' ? result.value : null)

/**
 * The server-side inputs for one asset's research brief: the daily and hourly
 * ratings and the daily backtest. Each can fail independently; a failed piece is
 * null and the brief says it is unavailable.
 */
export function useResearchInputs(symbol) {
  const [result, setResult] = useState({ symbol: null, signals: { '1d': null, '1h': null }, backtest: null })

  useEffect(() => {
    let cancelled = false

    Promise.allSettled([
      getSignals('1d', symbol),
      getSignals('1h', symbol),
      getBacktest(symbol, '1d'),
    ]).then(([daily, hourly, backtest]) => {
      if (cancelled) return
      setResult({
        symbol,
        signals: {
          '1d': settledValue(daily)?.signals?.[0] ?? null,
          '1h': settledValue(hourly)?.signals?.[0] ?? null,
        },
        backtest: settledValue(backtest),
      })
    })

    return () => {
      cancelled = true
    }
  }, [symbol])

  const loading = result.symbol !== symbol
  return {
    loading,
    signals: loading ? { '1d': null, '1h': null } : result.signals,
    backtest: loading ? null : result.backtest,
  }
}
