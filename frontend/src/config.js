// Base URL of the FinPulse API. Override with VITE_API_URL in frontend/.env.local.
export const API_BASE_URL = (
  import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
).replace(/\/$/, '')

// The live-price WebSocket lives on the same host as the REST API.
export const WS_PRICES_URL = `${API_BASE_URL.replace(/^http/, 'ws')}/ws/prices`
