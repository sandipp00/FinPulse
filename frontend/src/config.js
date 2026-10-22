// Base URL of the FinPulse API. Empty means "same origin", which is what you
// want: in development Vite proxies /api and /ws to the backend, and in
// production the bundled nginx does. Set VITE_API_URL only to point at an API
// on a different host (the session cookie then needs SameSite=None; Secure).
const configured = import.meta.env.VITE_API_URL

export const API_BASE_URL = configured === undefined ? '' : configured.replace(/\/$/, '')

// The live-price WebSocket lives on the same host as the REST API. Computed on
// demand (not at import time) so this module can be loaded without a browser.
export function getPricesSocketUrl() {
  if (API_BASE_URL) return `${API_BASE_URL.replace(/^http/, 'ws')}/ws/prices`
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/ws/prices`
}
