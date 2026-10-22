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

export function getBacktest(symbol, interval) {
  return getJSON(
    `/api/backtest?symbol=${encodeURIComponent(symbol)}`
    + `&interval=${encodeURIComponent(interval)}`,
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
