import { API_BASE_URL } from '../config'

async function getJSON(path) {
  const response = await fetch(`${API_BASE_URL}${path}`)

  if (!response.ok) {
    const message = await response.text()
    throw new Error(`API error ${response.status}: ${message}`)
  }

  return response.json()
}

export function getHealth() {
  return getJSON('/api/health')
}

export function getAssets() {
  return getJSON('/api/assets')
}

export function getPrices(symbol, limit = 180) {
  return getJSON(
    `/api/prices?symbol=${encodeURIComponent(symbol)}&limit=${limit}`,
  )
}

export function getSummary(symbol) {
  const query = symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''
  return getJSON(`/api/summary${query}`)
}

export function getLiveStatus() {
  return getJSON('/api/live/status')
}

export function getCandles(symbol, interval, limit = 500) {
  return getJSON(
    `/api/candles?symbol=${encodeURIComponent(symbol)}`
    + `&interval=${encodeURIComponent(interval)}&limit=${limit}`,
  )
}

export function getSignals(interval, symbol) {
  const query = `interval=${encodeURIComponent(interval)}`
    + (symbol ? `&symbol=${encodeURIComponent(symbol)}` : '')
  return getJSON(`/api/signals?${query}`)
}

export function getBacktest(symbol, interval) {
  return getJSON(
    `/api/backtest?symbol=${encodeURIComponent(symbol)}`
    + `&interval=${encodeURIComponent(interval)}`,
  )
}

// ---- Paper trading (virtual money) ------------------------------------

// FastAPI errors carry a human-readable `detail` (a string, or a list for
// validation errors); surface that instead of raw JSON.
function describeError(status, text) {
  try {
    const { detail } = JSON.parse(text)
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((item) => item.msg).join('; ')
  } catch {
    // not JSON; fall through
  }
  return `API error ${status}: ${text}`
}

async function postJSON(path, body) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok) throw new Error(describeError(response.status, await response.text()))
  return response.json()
}

export function getPaperPortfolio() {
  return getJSON('/api/paper/portfolio')
}

export function getPaperOrders(limit = 15) {
  return getJSON(`/api/paper/orders?limit=${limit}`)
}

export function getPaperEquity() {
  return getJSON('/api/paper/equity')
}

export function placePaperOrder(order) {
  return postJSON('/api/paper/orders', order)
}

export function followPaperSignal(symbol, interval, percent) {
  return postJSON('/api/paper/follow', { symbol, interval, percent })
}

export function resetPaperAccount(startingCash) {
  return postJSON('/api/paper/reset', startingCash ? { starting_cash: startingCash } : {})
}
