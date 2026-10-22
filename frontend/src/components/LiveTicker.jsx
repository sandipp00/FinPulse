import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { formatPercent, getAssetDetails } from '../lib/format'
import LiveBadge from './LiveBadge'
import LivePrice from './LivePrice'

/** Compact strip of live prices shown above the page content. */
export default function LiveTicker({ ticks, symbols, status }) {
  return (
    <div className="live-ticker" role="region" aria-label="Live crypto prices">
      <LiveBadge status={status} />
      <div className="live-ticker-items">
        {symbols.map((symbol) => {
          const tick = ticks[symbol]
          const positive = (tick?.change_pct_24h ?? 0) >= 0

          return (
            <div className="live-ticker-item" key={symbol}>
              <span className="live-ticker-symbol">{symbol.replace('/USDT', '')}</span>
              {tick ? (
                <>
                  <LivePrice tick={tick} />
                  <span className={`live-ticker-change ${positive ? 'up' : 'down'}`}>
                    {positive ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                    {formatPercent(tick.change_pct_24h)}
                  </span>
                </>
              ) : (
                <span className="live-ticker-wait">{getAssetDetails(symbol).name}…</span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
