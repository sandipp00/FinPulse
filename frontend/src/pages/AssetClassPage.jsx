import Watchlist from '../components/Watchlist'
import { formatAsOfDate } from '../lib/dataStatus'

// What each asset-class page covers, and where its numbers come from.
const CLASSES = {
  equities: {
    types: ['Stock', 'Index'],
    title: 'Equities watchlist',
    subtitle: 'Latest stored daily close for each stock and index',
    sources: [
      'Daily OHLCV history stored in the local SQLite database (downloaded with yfinance).',
      'There is no live equity quote yet: every price here is a stored close, tagged with its date.',
    ],
    empty: 'No stocks or indices are in the stored history. Run src/data/build_database.py to load them.',
  },
  crypto: {
    types: ['Crypto'],
    title: 'Crypto watchlist',
    subtitle: 'Live exchange prices where streamed, stored daily closes otherwise',
    sources: [
      'Live prices stream from Binance public market data (no API key); a price with no update for 30 seconds is marked stale.',
      'Daily OHLCV history for some coins is stored in the local SQLite database.',
    ],
    empty: 'No crypto assets yet. The live feed may still be connecting.',
  },
}

/** A filtered view of the tracked assets for one asset class, with its data coverage spelled out. */
export default function AssetClassPage({ assetClass, assets, ticks, liveStatus, loading, error, onSelect }) {
  const config = CLASSES[assetClass]
  const inClass = assets.filter((asset) => config.types.includes(asset.type))
  const stored = inClass.filter((asset) => asset.stored)
  const live = inClass.filter((asset) => ticks[asset.symbol])
  const newest = stored.map((asset) => asset.latest_timestamp).filter(Boolean).sort().at(-1)
  // While stored assets are loading or failed to load, their counts are unknown, not zero.
  const storedCount = (count) => (loading ? '…' : error ? '—' : count)

  return (
    <>
      <section className="panel coverage-panel" aria-label="Data coverage">
        <div className="coverage-stats">
          <div><span>Instruments</span><strong className="num">{storedCount(inClass.length)}</strong></div>
          <div><span>Streaming live</span><strong className="num">{live.length}</strong></div>
          <div><span>With stored history</span><strong className="num">{storedCount(stored.length)}</strong></div>
          <div><span>Stored history to</span><strong className="num">{newest ? formatAsOfDate(newest, { withYear: true }) : '—'}</strong></div>
        </div>
        <ul className="coverage-notes">
          {config.sources.map((note) => <li key={note}>{note}</li>)}
        </ul>
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
