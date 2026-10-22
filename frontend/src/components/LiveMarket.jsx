import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { formatCompact, formatPercent, formatPrice, getAssetDetails } from '../lib/format'
import LiveBadge from './LiveBadge'
import LivePrice from './LivePrice'
import Sparkline from './Sparkline'

function LiveCard({ symbol, tick, series }) {
  const details = getAssetDetails(symbol)
  const positive = (tick?.change_pct_24h ?? 0) >= 0
  // Sparkline colour follows the short-term (session) move, not the 24h change.
  const sessionUp = series.length < 2 || series.at(-1) >= series[0]

  return (
    <div className="live-card" style={{ '--accent': details.color }}>
      <div className="live-card-head">
        <span className="live-card-name">
          <i style={{ background: details.color }} />
          <strong>{symbol.replace('/USDT', '')}</strong>
          <small>{details.name}</small>
        </span>
        {tick && (
          <span className={`change-pill ${positive ? 'positive' : 'negative'}`}>
            {positive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
            {formatPercent(tick.change_pct_24h)}
          </span>
        )}
      </div>

      {tick ? (
        <>
          <LivePrice tick={tick} className="live-card-price" />
          <Sparkline values={series} positive={sessionUp} />
          <div className="live-card-stats">
            <span>H <b>{formatPrice(tick.high_24h, symbol)}</b></span>
            <span>L <b>{formatPrice(tick.low_24h, symbol)}</b></span>
            <span>Vol <b>${formatCompact(tick.quote_volume_24h)}</b></span>
          </div>
        </>
      ) : (
        <p className="live-card-wait">Waiting for first tick...</p>
      )}
    </div>
  )
}

export default function LiveMarket({ ticks, history, symbols, status }) {
  return (
    <section className="panel live-market">
      <div className="panel-heading">
        <div>
          <h2>Live crypto market</h2>
          <p>Real-time prices streamed from Binance · 24h change, range and volume</p>
        </div>
        <LiveBadge status={status} />
      </div>

      <div className="live-grid">
        {symbols.map((symbol) => (
          <LiveCard
            key={symbol}
            symbol={symbol}
            tick={ticks[symbol]}
            series={history[symbol] ?? []}
          />
        ))}
      </div>

      <p className="live-note">
        Sparklines show price moves since you opened this page. Live quotes are
        informational and may differ slightly from other venues.
      </p>
    </section>
  )
}
