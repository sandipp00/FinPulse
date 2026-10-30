import { ArrowDownRight, ArrowUpRight, BarChart3, Bitcoin } from 'lucide-react'
import { useNow } from '../hooks/useNow'
import { useWeekChanges } from '../hooks/useWeekChanges'
import { tickStatus } from '../lib/dataStatus'
import { formatPercent } from '../lib/format'
import DataTag from './DataTag'
import LivePrice from './LivePrice'

const FILTERS = ['All assets', 'Stock', 'Crypto', 'Index', 'Commodity']
const FILTER_LABEL = { Stock: 'Stocks', Index: 'Indices' }

const METAL_GLYPH = { 'GC=F': 'Au', 'XAU/USDT': 'Au', 'SI=F': 'Ag', 'XAG/USDT': 'Ag' }

function AssetGlyph({ symbol }) {
  if (symbol === 'BTC/USDT') return <Bitcoin size={20} />
  if (METAL_GLYPH[symbol]) return METAL_GLYPH[symbol]
  if (symbol.startsWith('^')) return <BarChart3 size={18} />
  return symbol === 'AAPL' ? 'A' : 'Ξ'
}

const weekTone = (change) => (change == null ? '' : change.change_pct >= 0 ? 'up' : 'down')
const dayFormat = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const weekTitle = (change) => (change
  ? `${dayFormat.format(change.base_time * 1000)} close ${change.base_close} → ${dayFormat.format(change.time * 1000)} ${change.close} (${change.source})`
  : 'No 7-day change available')

export default function Watchlist({
  assets,
  totalCount,
  loading,
  filter,
  onFilterChange,
  liveTicks,
  onSelect,
  title = 'Market watchlist',
  subtitle = 'Live prices where available, tagged CLOSED or DELAYED when they are not current',
  liveStatus,
}) {
  const now = useNow(5000)
  const week = useWeekChanges(assets.map((asset) => asset.symbol))

  return (
    <section className="panel assets-panel">
      <div className="panel-heading assets-heading">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        {onFilterChange && (
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
        )}
      </div>

      <div className="table-scroll">
        <table className="market-table">
          <thead>
            <tr>
              <th>ASSET</th>
              <th>TYPE</th>
              <th>PRICE</th>
              <th>CHANGE</th>
              <th title="From the close a week before the newest daily bar">7D CHANGE</th>
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
                        <DataTag status={tickStatus(tick, liveStatus, now)} />
                      </>
                    ) : asset.price}
                  </td>
                  <td>
                    <span className={`change-pill ${positive ? 'positive' : 'negative'}`}>
                      {positive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                      {tick ? `${formatPercent(tick.change_pct_24h)} ${tick.change_window === '1d' ? '1d' : '24h'}` : asset.change}
                    </span>
                  </td>
                  <td className={`price-cell num ${weekTone(week[asset.symbol])}`} title={weekTitle(week[asset.symbol])}>
                    {week[asset.symbol] ? formatPercent(week[asset.symbol].change_pct) : '—'}
                  </td>
                  <td>
                    <button
                      className="row-action"
                      onClick={() => onSelect(asset.symbol)}
                      title={`Open the ${asset.name ?? asset.symbol} asset page: price, chart and news`}
                      aria-label={`Open ${asset.symbol} asset page`}
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
        <span>LIVE: current price. CLOSED: market shut, last session price. HIST: stored daily close.</span>
      </div>
    </section>
  )
}
