import { useCallback, useEffect, useMemo, useState } from 'react'
import { getCandles } from '../api/finpulse'
import { applyTick, candleStart } from '../lib/candles'

const RECONCILE_DELAY_MS = 2000

/**
 * Candle history for a live symbol, with the latest live tick folded into the
 * current candle. `base` is the last server response (it only changes on a
 * fetch); `candles` also moves with every tick.
 */
export function useCandles(symbol, interval, tick) {
  const [result, setResult] = useState({ key: null, base: [], error: '' })
  const [reloadCount, setReloadCount] = useState(0)
  const key = `${symbol}|${interval}`

  useEffect(() => {
    let cancelled = false

    getCandles(symbol, interval)
      .then((response) => {
        if (cancelled) return
        setResult({ key, base: response.candles ?? [], error: '' })
      })
      .catch((err) => {
        if (cancelled) return
        setResult({ key, base: [], error: err.message || 'Unable to load candles.' })
      })

    return () => {
      cancelled = true
    }
  }, [symbol, interval, key, reloadCount])

  const loading = result.key !== key
  const base = loading ? EMPTY : result.base

  const candles = useMemo(() => applyTick(base, tick, interval), [base, tick, interval])

  // When live ticks start a new candle, re-fetch shortly after so the candle
  // that just closed gets its exchange-accurate open/high/low/volume.
  const lastTime = base.at(-1)?.time
  const liveStart = tick ? candleStart(tick.time, interval) : null
  const rolledOver = lastTime != null && liveStart != null && liveStart > lastTime

  useEffect(() => {
    if (!rolledOver) return undefined
    const timer = setTimeout(() => setReloadCount((n) => n + 1), RECONCILE_DELAY_MS)
    return () => clearTimeout(timer)
  }, [rolledOver, liveStart])

  const reload = useCallback(() => {
    setResult({ key: null, base: [], error: '' })
    setReloadCount((n) => n + 1)
  }, [])

  return { base, candles, loading, error: loading ? '' : result.error, reload }
}

const EMPTY = []
