import Watchlist from '../components/Watchlist'
import { formatAsOfDate, weekdaysSince } from '../lib/dataStatus'

// What each asset-class page covers, and where its numbers come from.
const CLASSES = {
  equities: {
    types: ['Stock', 'Index'],
    title: 'Equities watchlist',
    subtitle: 'Latest stored daily close for each stock and index',
    sources: [
      'End-of-day bars from Yahoo Finance (downloaded with yfinance), stored in the local database. Yahoo data is for personal use.',
      'There is no live equity quote: every price is a completed day\'s close, tagged with its date.',
      'Refresh with python src/data/update_equities.py (a dry run first; --apply to write).',
    ],
    showLag: true,
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
export default function AssetClassPage({ assetClass, assets, ticks, liveStatus, loading, error, onSelect, now }) {
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
          {config.showLag && newest && (
            <div>
              <span>Weekdays since</span>
              <strong className="num" title="Completed weekdays after the last stored close; exchange holidays are not excluded">
                {weekdaysSince(newest, now)}
              </strong>
            </div>
          )}
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
