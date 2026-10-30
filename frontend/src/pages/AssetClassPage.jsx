import { useState } from 'react'
import CryptoDerivatives from '../components/CryptoDerivatives'
import Watchlist from '../components/Watchlist'
import { useAssetRegistry } from '../hooks/useAsset'
import { equityRows, sectorCounts } from '../lib/equities'
import { formatPercent, getAssetDetails } from '../lib/format'
import { summarize } from '../lib/marketSummary'

// What each asset-class page covers, and where its numbers come from.
const CLASSES = {
  equities: {
    title: 'US stocks',
    subtitle: 'The 30 largest US companies by market cap, largest first. Indices are on the World indices page.',
    changeLabel: 'since the previous close',
    source: 'Quotes from Yahoo Finance every 15 seconds (personal use). CLOSED: market shut, last session price; DELAYED: the newest price is a few minutes old.',
    empty: 'The stock list could not be loaded.',
  },
  crypto: {
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
export default function AssetClassPage({ assetClass, assets, ticks, liveStatus, loading: assetsLoading, error: assetsError, onSelect }) {
  const config = CLASSES[assetClass]
  const registry = useAssetRegistry()
  const [sector, setSector] = useState('all')
  const equities = assetClass === 'equities'
  // Stocks come from the asset registry (with sectors); crypto from the live and stored assets.
  const rows = equities
    ? equityRows(registry.assets, assets).map((row) => ({ ...row, color: getAssetDetails(row.symbol).color }))
    : assets.filter((asset) => asset.type === 'Crypto')
  const sectors = equities ? sectorCounts(rows) : []
  const shownSector = sectors.some((s) => s.sector === sector) ? sector : 'all'
  const inClass = shownSector === 'all' ? rows : rows.filter((row) => row.sector === shownSector)
  const loading = equities ? registry.loading : assetsLoading
  const error = equities ? registry.error : assetsError
  const summary = summarize(inClass, ticks)
  // While the list is loading or failed to load, its counts are unknown, not zero.
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
        <p className="coverage-foot">Changes {config.changeLabel}{shownSector === 'all' ? '' : `, ${shownSector} only`}. {config.source}</p>
      </section>

      {sectors.length > 0 && (
        <div className="at-tabs sector-tabs" role="tablist" aria-label="Sector">
          {[{ sector: 'all', count: rows.length }, ...sectors].map(({ sector: key, count }) => (
            <button key={key} role="tab" aria-selected={shownSector === key} className={shownSector === key ? 'at-tab-active' : ''} onClick={() => setSector(key)}>
              {key === 'all' ? 'All' : key}
              <span className="at-tab-count">{count}</span>
            </button>
          ))}
        </div>
      )}

      <div className="page-block">
        {!loading && inClass.length === 0 ? (
          <section className="panel empty-panel">
            {error ? `This list is unavailable: ${error}` : config.empty}
          </section>
        ) : (
          <Watchlist
            assets={inClass}
            totalCount={rows.length}
            loading={loading}
            liveTicks={ticks}
            liveStatus={liveStatus}
            onSelect={onSelect}
            title={config.title}
            subtitle={config.subtitle}
          />
        )}
      </div>

      {assetClass === 'crypto' && <div className="page-block"><CryptoDerivatives /></div>}
    </>
  )
}
