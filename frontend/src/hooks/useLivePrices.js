import { useEffect, useState } from 'react'
import { getPricesSocketUrl } from '../config'

const HISTORY_LENGTH = 60
const RETRY_MIN_MS = 1000
const RETRY_MAX_MS = 15000

// Merge one tick into the per-symbol state. `direction` and `seq` only change
// when the price changes, so a flash animation keyed on `seq` fires exactly
// once per real price move. `seenAt` is when this browser received the tick, used
// to spot a stale price without trusting the server's or the exchange's clock.
function mergeTick(ticks, incoming) {
  const tick = { ...incoming, seenAt: Date.now() }
  const previous = ticks[tick.symbol]

  if (!previous) {
    return { ...ticks, [tick.symbol]: { ...tick, direction: 'flat', seq: 0 } }
  }

  const moved = tick.price !== previous.price
  const direction = !moved ? previous.direction : tick.price > previous.price ? 'up' : 'down'

  return {
    ...ticks,
    [tick.symbol]: {
      ...tick,
      direction,
      seq: moved ? previous.seq + 1 : previous.seq,
    },
  }
}

function appendHistory(history, tick) {
  const series = history[tick.symbol] ?? []
  if (series.at(-1) === tick.price) return history
  return { ...history, [tick.symbol]: [...series, tick.price].slice(-HISTORY_LENGTH) }
}

/**
 * Subscribes to the backend's /ws/prices socket and reconnects with
 * exponential backoff.
 *
 * status: 'connecting' | 'live' | 'reconnecting' | 'offline'
 *   'offline' means our socket is open but the server's upstream exchange
 *   connection is down (no fresh data is coming).
 *
 * `status` is the crypto feed's (it drives the app-wide badge). `marketStatus`
 * has one status per market: crypto, tradfi (Binance gold, silver and oil
 * futures) and quotes (Yahoo stocks, indices and FX), which fail independently.
 */
export function useLivePrices() {
  const [ticks, setTicks] = useState({})
  const [history, setHistory] = useState({})
  const [status, setStatus] = useState('connecting')
  const [marketStatus, setMarketStatus] = useState({ crypto: 'connecting', tradfi: 'connecting', quotes: 'connecting' })

  useEffect(() => {
    let socket = null
    let retryTimer = null
    let attempt = 0
    let disposed = false

    const handleMessage = (event) => {
      let message
      try {
        message = JSON.parse(event.data)
      } catch {
        return
      }

      if (message.type === 'snapshot') {
        setStatus(message.connected ? 'live' : 'offline')
        if (message.markets) {
          setMarketStatus((current) => ({
            ...current,
            ...Object.fromEntries(Object.entries(message.markets).map(([market, up]) => [market, up ? 'live' : 'offline'])),
          }))
        }
        for (const tick of message.ticks) {
          setTicks((current) => mergeTick(current, tick))
          setHistory((current) => appendHistory(current, tick))
        }
      } else if (message.type === 'status') {
        const market = message.market ?? 'crypto'
        if (market === 'crypto') setStatus(message.connected ? 'live' : 'offline')
        setMarketStatus((current) => ({ ...current, [market]: message.connected ? 'live' : 'offline' }))
      } else if (message.type === 'tick') {
        const market = message.market ?? 'crypto'
        if (market === 'crypto') setStatus('live')
        setMarketStatus((current) => (current[market] === 'live' ? current : { ...current, [market]: 'live' }))
        setTicks((current) => mergeTick(current, message))
        setHistory((current) => appendHistory(current, message))
      }
    }

    const connect = () => {
      socket = new WebSocket(getPricesSocketUrl())
      socket.onopen = () => {
        attempt = 0
      }
      socket.onmessage = handleMessage
      socket.onclose = () => {
        if (disposed) return
        setStatus('reconnecting')
        setMarketStatus({ crypto: 'reconnecting', tradfi: 'reconnecting', quotes: 'reconnecting' })
        const delay = Math.min(RETRY_MIN_MS * 2 ** attempt, RETRY_MAX_MS)
        attempt += 1
        retryTimer = setTimeout(connect, delay)
      }
      // onclose always follows onerror, so retry logic lives there.
      socket.onerror = () => socket.close()
    }

    connect()

    return () => {
      disposed = true
      clearTimeout(retryTimer)
      socket?.close()
    }
  }, [])

  return { ticks, history, status, marketStatus }
}
