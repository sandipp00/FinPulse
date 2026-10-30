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

function LiveItem({ symbol, tick, status, now }) {
  const freshness = tickStatus(tick, status, now)
  return (
    <div className="live-ticker-item">
      <span className="live-ticker-symbol">{symbol.replace('/USDT', '')}</span>
      {tick ? (
        <>
          <LivePrice tick={tick} />
          <Change value={tick.change_pct_24h} suffix=" 24h" />
          {freshness === 'stale' && <DataTag status="stale" />}
        </>
      ) : (
        <span className="live-ticker-wait">{getAssetDetails(symbol).name}…</span>
      )}
    </div>
  )
}

/**
 * Strip of prices above the page content: live crypto from the exchange feed, live
 * gold and silver (judged by their own feed's status), then the latest stored close
 * for stocks, indices and COMEX metals, tagged with its date.
 */
export default function LiveTicker({ ticks, symbols, status, metalSymbols = [], metalsStatus, storedAssets = [] }) {
  const now = useNow(5000)

  return (
    <div className="live-ticker" role="region" aria-label="Market prices">
      <LiveBadge status={status} />
      <div className="live-ticker-items">
        {symbols.map((symbol) => <LiveItem key={symbol} symbol={symbol} tick={ticks[symbol]} status={status} now={now} />)}

        {metalSymbols.length > 0 && <span className="live-ticker-divider" aria-hidden="true" />}
        {metalSymbols.map((symbol) => (
          <LiveItem key={symbol} symbol={symbol} tick={ticks[symbol]} status={metalsStatus} now={now} />
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
