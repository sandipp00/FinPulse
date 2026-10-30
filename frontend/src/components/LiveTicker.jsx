import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { useNow } from '../hooks/useNow'
import { formatAsOfDate, tickStatus } from '../lib/dataStatus'
import { formatPercent, formatPrice, getAssetDetails } from '../lib/format'
import DataTag from './DataTag'
import LiveBadge from './LiveBadge'
import LivePrice from './LivePrice'

function Change({ value, suffix }) {
  if (value == null || !Number.isFinite(Number(value))) return null
  const positive = Number(value) >= 0
  return (
    <span className={`live-ticker-change ${positive ? 'up' : 'down'}`}>
      {positive ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
      {formatPercent(value)}{suffix}
    </span>
  )
}

// Live and closed markets are the normal case; only the exceptions get a tag.
const TAGGED = new Set(['stale', 'delayed', 'closed'])

function LiveItem({ symbol, tick, status, now }) {
  const freshness = tickStatus(tick, status, now)
  return (
    <div className="live-ticker-item">
      <span className="live-ticker-symbol">{symbol.replace('/USDT', '')}</span>
      {tick ? (
        <>
          <LivePrice tick={tick} />
          <Change value={tick.change_pct_24h} suffix={tick.change_window === '1d' ? ' 1d' : ' 24h'} />
          {TAGGED.has(freshness) && <DataTag status={freshness} />}
        </>
      ) : (
        <span className="live-ticker-wait">{getAssetDetails(symbol).name}…</span>
      )}
    </div>
  )
}

/**
 * Strip of prices above the page content: live crypto, then live gold, silver and
 * oil (Binance futures), then stocks, indices and FX (Yahoo quotes), each judged
 * by its own feed; then the stored close, dated, for anything without a live quote.
 */
export default function LiveTicker({
  ticks, symbols, status, tradfiSymbols = [], quoteSymbols = [], marketStatus = {}, storedAssets = [],
}) {
  const now = useNow(5000)

  return (
    <div className="live-ticker" role="region" aria-label="Market prices">
      <LiveBadge status={status} />
      <div className="live-ticker-items">
        {symbols.map((symbol) => <LiveItem key={symbol} symbol={symbol} tick={ticks[symbol]} status={status} now={now} />)}

        {[tradfiSymbols, quoteSymbols].map((group) => group.length > 0 && (
          <span key={group[0]} className="live-ticker-group">
            <span className="live-ticker-divider" aria-hidden="true" />
            {group.map((symbol) => (
              <LiveItem key={symbol} symbol={symbol} tick={ticks[symbol]} status={marketStatus} now={now} />
            ))}
          </span>
        ))}

        {storedAssets.length > 0 && <span className="live-ticker-divider" aria-hidden="true" />}

        {storedAssets.map((asset) => (
          <div className="live-ticker-item" key={asset.symbol}>
            <span className="live-ticker-symbol">{asset.symbol}</span>
            <span className="num">{formatPrice(asset.latest_price, asset.symbol)}</span>
            <Change value={asset.daily_change_pct} suffix=" 1d" />
            <DataTag status="historical" detail={formatAsOfDate(asset.latest_timestamp)} />
          </div>
        ))}
      </div>
    </div>
  )
}
