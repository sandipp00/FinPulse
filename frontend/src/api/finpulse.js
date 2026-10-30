import { API_BASE_URL } from '../config'

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

// Raised on window when a signed-in request comes back 401 (session expired or
// revoked), so the app can drop back to the signed-out state.
export const SIGNED_OUT_EVENT = 'finpulse:signed-out'

function noteUnauthorized(path, status) {
  // A 401 from /api/auth/* is just a failed login, not an expired session.
  if (status === 401 && !path.startsWith('/api/auth/')) {
    window.dispatchEvent(new Event(SIGNED_OUT_EVENT))
  }
}

async function getJSON(path) {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include' })

  if (!response.ok) {
    noteUnauthorized(path, response.status)
    throw new Error(describeError(response.status, await response.text()))
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

export function getBacktest(symbol, interval, { slippageBps = 0, positionPct = 100 } = {}) {
  return getJSON(
    `/api/backtest?symbol=${encodeURIComponent(symbol)}`
    + `&interval=${encodeURIComponent(interval)}`
    + `&slippage_bps=${slippageBps}&position_pct=${positionPct}`,
  )
}

// ---- Paper trading (virtual money) ------------------------------------

async function postJSON(path, body) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })

  if (!response.ok) {
    noteUnauthorized(path, response.status)
    throw new Error(describeError(response.status, await response.text()))
  }
  return response.json()
}

async function putJSON(path, body) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })

  if (!response.ok) {
    noteUnauthorized(path, response.status)
    throw new Error(describeError(response.status, await response.text()))
  }
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

// ---- Accounts -------------------------------------------------------------

export function getMe() {
  return getJSON('/api/auth/me')
}

export function registerAccount(email, password) {
  return postJSON('/api/auth/register', { email, password })
}

export function loginAccount(email, password) {
  return postJSON('/api/auth/login', { email, password })
}

export function logoutAccount() {
  return postJSON('/api/auth/logout')
}

export function verifyEmail(token) {
  return postJSON('/api/auth/verify-email', { token })
}

export function resendVerification() {
  return postJSON('/api/auth/resend-verification')
}

export function forgotPassword(email) {
  return postJSON('/api/auth/forgot-password', { email })
}

export function resetPassword(token, password) {
  return postJSON('/api/auth/reset-password', { token, password })
}

export function getRisk() {
  return getJSON('/api/risk')
}

export function getInstruments() {
  return getJSON('/api/instruments')
}

export function getInstrumentHistory(symbol, interval, limit) {
  return getJSON(
    `/api/instruments/history?symbol=${encodeURIComponent(symbol)}`
    + `&interval=${encodeURIComponent(interval)}&limit=${limit}`,
  )
}

export function getMacroSeries() {
  return getJSON('/api/macro/series')
}

export function getMacroSeriesDetail(seriesId) {
  return getJSON(`/api/macro/series/${encodeURIComponent(seriesId)}`)
}

export function getFxPairs() {
  return getJSON('/api/fx/pairs')
}

export function getFxHistory(pair) {
  return getJSON(`/api/fx/history?pair=${encodeURIComponent(pair)}`)
}

export function getCommodities() {
  return getJSON('/api/commodities')
}

export function getCommodityHistory(series) {
  return getJSON(`/api/commodities/history?series=${encodeURIComponent(series)}`)
}

export function getNews(limit = 200) {
  return getJSON(`/api/news?limit=${limit}`)
}

export function getCalendar(daysBack = 14, daysAhead = 90) {
  return getJSON(`/api/calendar?days_back=${daysBack}&days_ahead=${daysAhead}`)
}

export function getRelative(symbol, benchmark, window = 60) {
  return getJSON(
    `/api/quant/relative?symbol=${encodeURIComponent(symbol)}`
    + `&benchmark=${encodeURIComponent(benchmark)}&window=${window}`,
  )
}

export function getAssistantStatus() {
  return getJSON('/api/assistant/status')
}

export function askAssistant(question, mode = 'rules') {
  return postJSON('/api/assistant/ask', { question, mode })
}

export function getMarketHours() {
  return getJSON('/api/market-hours')
}

export function getWorldIndices() {
  return getJSON('/api/world-indices')
}

export function getAssetRegistry() {
  return getJSON('/api/asset-registry')
}

export function getAssetNews(asset) {
  return getJSON(`/api/asset-news?asset=${encodeURIComponent(asset)}`)
}

export function getAnalysisScoreboard() {
  return getJSON('/api/analysis/scoreboard')
}

export function getAssetAnalysis(asset) {
  return getJSON(`/api/analysis/asset?asset=${encodeURIComponent(asset)}`)
}

export function getWeekChanges(symbols) {
  return getJSON(`/api/instruments/week-change?symbols=${encodeURIComponent(symbols.join(','))}`)
}

export function getCryptoDerivatives(currency) {
  return getJSON(`/api/crypto/derivatives?currency=${encodeURIComponent(currency)}`)
}

export function getCftc() {
  return getJSON('/api/cftc')
}

export function getWatchlist() {
  return getJSON('/api/watchlist')
}

export function saveWatchlist(symbols) {
  return putJSON('/api/watchlist', { symbols })
}

export function getEarnings(symbol) {
  return getJSON(symbol ? `/api/earnings?symbol=${encodeURIComponent(symbol)}` : '/api/earnings')
}
