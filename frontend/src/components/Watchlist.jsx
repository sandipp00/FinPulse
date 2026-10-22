import { ArrowDownRight, ArrowUpRight, BarChart3, Bitcoin } from 'lucide-react'
import { formatPercent } from '../lib/format'
import LivePrice from './LivePrice'

const FILTERS = ['All assets', 'Stock', 'Crypto', 'Index']
const FILTER_LABEL = { Stock: 'Stocks', Index: 'Indices' }

function AssetGlyph({ symbol }) {
  if (symbol === 'BTC/USDT') return <Bitcoin size={20} />
  if (symbol === '^NSEI') return <BarChart3 size={18} />
  return symbol === 'AAPL' ? 'A' : 'Ξ'
}

export default function Watchlist({
  assets,
  totalCount,
  loading,
  filter,
  onFilterChange,
  liveTicks,
  onSelect,
}) {
  return (
    <section className="panel assets-panel">
      <div className="panel-heading assets-heading">
        <div>
          <h2>Market watchlist</h2>
          <p>Live prices for crypto, latest stored prices for everything else</p>
        </div>
        <div className="asset-filters">
          {FILTERS.map((item) => (
            <button
              key={item}
              onClick={() => onFilterChange(item)}
              className={filter === item ? 'filter-active' : ''}
            >
              {FILTER_LABEL[item] ?? item}
            </button>
          ))}
        </div>
      </div>

      <div className="table-scroll">
        <table className="market-table">
          <thead>
            <tr>
              <th>ASSET</th>
              <th>TYPE</th>
              <th>PRICE</th>
              <th>CHANGE</th>
              <th>HISTORICAL RETURN</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {assets.map((asset) => {
              const tick = liveTicks[asset.symbol]
              const positive = tick
                ? tick.change_pct_24h >= 0
                : asset.positive

              return (
                <tr key={asset.symbol}>
                  <td>
                    <div className="asset-cell">
                      <span
                        className="asset-icon"
                        style={{
                          color: asset.color,
                          borderColor: `${asset.color}44`,
                          background: `${asset.color}12`,
                        }}
                      >
                        <AssetGlyph symbol={asset.symbol} />
                      </span>
                      <span><strong>{asset.symbol}</strong><small>{asset.name}</small></span>
                    </div>
                  </td>
                  <td><span className="type-label">{asset.type}</span></td>
                  <td className="price-cell">
                    {tick ? (
                      <>
                        <LivePrice tick={tick} />
                        <span className="row-live-tag">LIVE</span>
                      </>
                    ) : asset.price}
                  </td>
                  <td>
                    <span className={`change-pill ${positive ? 'positive' : 'negative'}`}>
                      {positive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                      {tick ? `${formatPercent(tick.change_pct_24h)} 24h` : asset.change}
                    </span>
                  </td>
                  <td className="price-cell">{formatPercent(asset.total_return_pct)}</td>
                  <td>
                    <button
                      className="row-action"
                      onClick={() => onSelect(asset.symbol)}
                      disabled={!asset.stored}
                      title={asset.stored ? undefined : 'No stored history for this asset'}
                      aria-label={`View ${asset.symbol} historical prices`}
                    >
                      <ArrowUpRight size={17} />
                    </button>
                  </td>
                </tr>
              )
            })}
            {!loading && assets.length === 0 && (
              <tr><td colSpan="6" className="empty-state">No assets match your search.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="table-footer">
        <span>{loading ? 'Loading assets...' : `Showing ${assets.length} of ${totalCount} tracked assets`}</span>
        <span>Stocks and indices show the latest stored close, not a live quote.</span>
      </div>
    </section>
  )
}
