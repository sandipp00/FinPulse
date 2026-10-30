import Watchlist from '../components/Watchlist'
import { formatPercent } from '../lib/format'
import { summarize } from '../lib/marketSummary'

// What each asset-class page covers, and where its numbers come from.
const CLASSES = {
  equities: {
    types: ['Stock', 'Index'],
    title: 'Equities watchlist',
    subtitle: 'Near-real-time quotes while markets are open; the last session price when closed',
    changeLabel: 'since the previous close',
    source: 'Quotes from Yahoo Finance every 15 seconds (personal use). CLOSED: market shut, last session price; DELAYED: the newest price is a few minutes old.',
    empty: 'No stocks or indices are in the stored history. Run src/data/build_database.py to load them.',
  },
  crypto: {
    types: ['Crypto'],
    title: 'Crypto watchlist',
    subtitle: 'Live exchange prices where streamed, stored daily closes otherwise',
    changeLabel: 'over 24 hours',
    source: 'Live prices stream from Binance public market data; a price with no update for 30 seconds is marked STALE.',
    empty: 'No crypto assets yet. The live feed may still be connecting.',
  },
}

const tone = (value) => (value == null ? '' : value >= 0 ? 'up' : 'down')

function Mover({ label, move }) {
  return (
    <div>
      <span>{label}</span>
      {move ? (
        <strong className={`num ${tone(move.change)}`} title={move.symbol}>
          {move.name.split(' (')[0]} {formatPercent(move.change)}
        </strong>
      ) : <strong className="num">—</strong>}
    </div>
  )
}

/** One asset class: a quick read of how it is moving, then its watchlist. */
export default function AssetClassPage({ assetClass, assets, ticks, liveStatus, loading, error, onSelect }) {
  const config = CLASSES[assetClass]
  const inClass = assets.filter((asset) => config.types.includes(asset.type))
  const summary = summarize(inClass, ticks)
  // While stored assets are loading or failed to load, their counts are unknown, not zero.
  const known = (value) => (loading ? '…' : error ? '—' : value)

  return (
    <>
      <section className="panel coverage-panel" aria-label="Market summary">
        <div className="coverage-stats">
          <div><span>Instruments</span><strong className="num">{known(summary.count)}</strong></div>
          <div>
            <span>Up · down</span>
            <strong className="num"><span className="up">{summary.up}</span> · <span className="down">{summary.down}</span></strong>
          </div>
          <div>
            <span>Average change</span>
            <strong className={`num ${tone(summary.average)}`}>{summary.average == null ? '—' : formatPercent(summary.average)}</strong>
          </div>
          <Mover label="Biggest gainer" move={summary.best} />
          <Mover label="Biggest loser" move={summary.worst} />
        </div>
        <p className="coverage-foot">Changes {config.changeLabel}. {config.source}</p>
      </section>

      <div className="page-block">
        {!loading && inClass.length === 0 ? (
          <section className="panel empty-panel">
            {error ? 'Stored assets could not be loaded, so this list is unavailable.' : config.empty}
          </section>
        ) : (
          <Watchlist
            assets={inClass}
            totalCount={inClass.length}
            loading={loading}
            liveTicks={ticks}
            liveStatus={liveStatus}
            onSelect={onSelect}
            title={config.title}
            subtitle={config.subtitle}
          />
        )}
      </div>
    </>
  )
}
