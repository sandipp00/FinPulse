import { memo } from 'react'
import { BarChart3 } from 'lucide-react'
import { LIVE_STATUS_BADGE, LIVE_STATUS_LABEL } from '../lib/liveStatus'

// The live feeds, which fail independently (see useLivePrices).
const FEEDS = [
  ['crypto', 'Crypto', 'BINANCE SPOT'],
  ['tradfi', 'Gold, silver, oil', 'BINANCE FUTURES'],
  ['quotes', 'Stocks, indices, FX', 'YAHOO'],
]

function DataStatus({ apiError, loading, liveStatus, marketStatus }) {
  const apiLabel = apiError
    ? 'API request needs attention'
    : loading
      ? 'Checking API connection...'
      : 'Connected · read-only history'

  return (
    <div className="panel data-status">
      <div className="flex items-center gap-2">
        <div className="icon-tile"><BarChart3 size={17} /></div>
        <h2>Data connectivity</h2>
      </div>
      <p>The local API (stored history, charts, news, macro) and the three live price feeds</p>
      <div className="connection-row">
        <span className={`status-dot ${apiError ? 'status-muted' : ''}`} />
        <span>{apiLabel}</span>
        <span className="connection-badge">{apiError ? 'CHECK' : 'LOCAL API'}</span>
      </div>
      {marketStatus ? FEEDS.map(([key, label, badge]) => (
        <div key={key} className="connection-row connection-row-flush">
          <span className={`status-dot ${marketStatus[key] === 'live' ? '' : 'status-muted'}`} />
          <span>{label} · {(LIVE_STATUS_BADGE[marketStatus[key]] ?? marketStatus[key]).toLowerCase()}</span>
          <span className="connection-badge">{badge}</span>
        </div>
      )) : (
        <div className="connection-row connection-row-flush">
          <span className={`status-dot ${liveStatus === 'live' ? '' : 'status-muted'}`} />
          <span>{LIVE_STATUS_LABEL[liveStatus]}</span>
          <span className="connection-badge">WEBSOCKET</span>
        </div>
      )}
    </div>
  )
}

export default memo(DataStatus)
