import { useNow } from '../hooks/useNow'
import { ageInDays, apiState, formatAge, formatAsOfDate } from '../lib/dataStatus'
import { LIVE_STATUS_LABEL } from '../lib/liveStatus'

const FEED_TONE = { live: 'ok', connecting: 'muted', reconnecting: 'warn', offline: 'error' }
const FEED_TEXT = { live: 'connected', connecting: 'connecting…', reconnecting: 'reconnecting…', offline: 'exchange offline' }

const localClock = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const utcClock = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })
const numberFormat = new Intl.NumberFormat('en-US')

function hostOf(url) {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

function Item({ tone, title, children }) {
  return (
    <span className={`status-item tone-${tone}`} title={title}>
      {tone && <i />}
      {children}
    </span>
  )
}

/**
 * The bottom bar: is the API answering, is the exchange feed flowing, how old the
 * stored history is, and the time. Everything here comes from the backend or the
 * socket; a check that has not answered says so instead of guessing.
 */
export default function StatusBar({ backend, liveStatus, ticks, storedAsOf, assetsLoading, assetsError }) {
  const now = useNow(1000)

  const api = apiState(backend)
  const records = backend.health?.records
  const apiText = api === 'ok'
    ? `API OK · ${numberFormat.format(records ?? 0)} stored bars`
    : api === 'checking' ? 'Checking API…' : 'API unreachable'

  let lastSeen = null
  for (const tick of Object.values(ticks)) {
    if (Number.isFinite(tick.seenAt) && (lastSeen == null || tick.seenAt > lastSeen)) lastSeen = tick.seenAt
  }
  const source = backend.live?.source ? hostOf(backend.live.source) : null
  const feedTitle = [
    LIVE_STATUS_LABEL[liveStatus],
    source && `source ${source}`,
    backend.live?.last_error && `last error: ${backend.live.last_error}`,
    backend.liveError && `status check failed: ${backend.liveError}`,
  ].filter(Boolean).join(' · ')

  const historyDays = storedAsOf ? ageInDays(storedAsOf, now) : null
  const historyText = assetsLoading
    ? 'Loading stored history…'
    : assetsError
      ? 'Stored history unavailable'
      : storedAsOf
        ? `History to ${formatAsOfDate(storedAsOf, { withYear: true })} (${historyDays}d old)`
        : 'No stored history'

  return (
    <footer className="status-bar" aria-label="Connection status">
      <Item tone={api === 'ok' ? 'ok' : api === 'checking' ? 'muted' : 'error'} title={backend.healthError || apiText}>
        {apiText}
      </Item>
      <Item tone={FEED_TONE[liveStatus]} title={feedTitle}>
        Feed {FEED_TEXT[liveStatus]}
        {lastSeen != null && <span className="status-sub">last tick {formatAge(now - lastSeen)}</span>}
        {source && <span className="status-sub status-wide">{source}</span>}
      </Item>
      <Item tone={assetsError ? 'error' : storedAsOf ? 'hist' : 'muted'} title="Stocks and indices show stored daily closes, not live quotes">
        {historyText}
      </Item>
      <span className="status-item status-wide">Crypto trades 24/7 · equities: daily history only</span>

      <span className="status-spacer" />
      <span className="status-item status-wide">Informational only · not investment advice</span>
      <span className="status-item num" title="Local time, then UTC">
        {localClock.format(now)}
        <span className="status-sub">{utcClock.format(now)} UTC</span>
      </span>
    </footer>
  )
}
