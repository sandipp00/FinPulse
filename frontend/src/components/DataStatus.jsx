import { memo } from 'react'
import { BarChart3 } from 'lucide-react'
import { LIVE_STATUS_LABEL } from '../lib/liveStatus'

function DataStatus({ apiError, loading, liveStatus }) {
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
      <p>FastAPI serving local SQLite history and a live Binance crypto feed</p>
      <div className="connection-row">
        <span className={`status-dot ${apiError ? 'status-muted' : ''}`} />
        <span>{apiLabel}</span>
        <span className="connection-badge">{apiError ? 'CHECK' : 'LOCAL API'}</span>
      </div>
      <div className="connection-row connection-row-flush">
        <span className={`status-dot ${liveStatus === 'live' ? '' : 'status-muted'}`} />
        <span>{LIVE_STATUS_LABEL[liveStatus]}</span>
        <span className="connection-badge">WEBSOCKET</span>
      </div>
    </div>
  )
}

export default memo(DataStatus)
