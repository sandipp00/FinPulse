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
