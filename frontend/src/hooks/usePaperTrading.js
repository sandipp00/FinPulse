import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  followPaperSignal,
  getPaperEquity,
  getPaperOrders,
  getPaperPortfolio,
  placePaperOrder,
  resetPaperAccount,
} from '../api/finpulse'
import { valuePortfolio } from '../lib/portfolio'

const EQUITY_REFRESH_MS = 60_000

/**
 * Paper-trading account state. The server owns the truth (cash, positions,
 * orders); `view` re-values it with live ticks so P&L updates every tick.
 */
export function usePaperTrading(ticks) {
  const [portfolio, setPortfolio] = useState(null)
  const [orders, setOrders] = useState([])
  const [equity, setEquity] = useState([])
  const [error, setError] = useState('')

  const refreshHistory = useCallback(() => (
    Promise.all([getPaperOrders(), getPaperEquity()])
      .then(([orderResult, equityResult]) => {
        setOrders(orderResult.orders)
        setEquity(equityResult.points)
      })
      .catch(() => {
        // History is secondary; the portfolio call surfaces connection errors.
      })
  ), [])

  useEffect(() => {
    let cancelled = false

    getPaperPortfolio()
      .then((result) => {
        if (cancelled) return
        setPortfolio(result)
        setError('')
        return refreshHistory()
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Unable to load the paper account.')
      })

    const timer = setInterval(() => {
      if (!cancelled) refreshHistory()
    }, EQUITY_REFRESH_MS)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [refreshHistory])

  // Each action resolves with the server's response, or rejects with a message
  // fit to show the user; the caller decides how to present it.
  const applyResult = useCallback((result) => {
    setPortfolio(result.portfolio ?? result)
    setError('')
    return refreshHistory().then(() => result)
  }, [refreshHistory])

  const trade = useCallback((order) => placePaperOrder(order).then(applyResult), [applyResult])

  const follow = useCallback(
    (symbol, interval, percent) => followPaperSignal(symbol, interval, percent).then(applyResult),
    [applyResult],
  )

  const reset = useCallback(
    (startingCash) => resetPaperAccount(startingCash).then(applyResult),
    [applyResult],
  )

  const view = useMemo(() => valuePortfolio(portfolio, ticks), [portfolio, ticks])

  return { view, orders, equity, error, trade, follow, reset }
}
