import { useMemo, useState } from 'react'
import DataTag from '../components/DataTag'
import SeriesChart from '../components/SeriesChart'
import { useCommodities, useCommodityHistory } from '../hooks/useCommodities'
import { navigate } from '../hooks/useRoute'
import { isCachedFallback, parseTimestamp } from '../lib/dataStatus'
import { formatQuote } from '../lib/explorer'
import { formatPercent, getAssetDetails } from '../lib/format'
import { formatObservationDate, toChartPoints, withinYears } from '../lib/macro'
import { ROUTES } from '../lib/routes'

const RANGES = [
  { label: '1Y', years: 1 },
  { label: '5Y', years: 5 },
  { label: '10Y', years: null },
]

const fetchedFormat = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })

const tagFor = (item) => (item.status === 'unavailable' ? 'unavailable' : isCachedFallback(item.meta) ? 'cached' : 'historical')

function Card({ item, active, onSelect }) {
  const available = item.status !== 'unavailable'
  const up = item.change != null && item.change >= 0
  return (
    <button
      className={`macro-card ${active ? 'macro-card-active' : ''}`}
      onClick={() => onSelect(item.id)}
      disabled={!available}
      aria-pressed={active}
      title={available ? item.label : item.error}
    >
      <span className="macro-card-top">
        <span>Crude oil spot</span>
        <DataTag status={tagFor(item)} />
      </span>
      <strong className="macro-card-title">{item.label}</strong>
      <span className="macro-card-value num">{formatQuote(item.latest?.value, item.currency)}</span>
      <span className="macro-card-meta">
        {available ? (
          <>
            {formatObservationDate(item.latest?.date, 'Daily')}
            {item.change != null && (
              <b className={`num ${up ? 'up' : 'down'}`}>
                {up ? '▲' : '▼'} {formatQuote(Math.abs(item.change), item.currency)} ({formatPercent(item.change_pct)})
              </b>
            )}
          </>
        ) : (item.error ?? 'Unavailable')}
      </span>
      <small className="macro-card-id">{item.id} · {item.currency} {item.unit}</small>
    </button>
  )
}

function MetalCard({ asset }) {
  const change = asset.daily_change_pct
  const up = change != null && change >= 0
  const day = asset.latest_timestamp ? String(asset.latest_timestamp).slice(0, 10) : null
  return (
    <button
      className="macro-card"
      onClick={() => navigate(`${ROUTES.explorer}?symbol=${encodeURIComponent(asset.symbol)}`)}
      title={`Open ${asset.symbol} in the explorer`}
    >
      <span className="macro-card-top">
        <span>COMEX futures</span>
        <DataTag status={asset.latest_price == null ? 'unavailable' : 'historical'} />
      </span>
      <strong className="macro-card-title">{getAssetDetails(asset.symbol).name}</strong>
      <span className="macro-card-value num">{formatQuote(asset.latest_price, 'USD')}</span>
      <span className="macro-card-meta">
        {formatObservationDate(day, 'Daily')}
        {change != null && <b className={`num ${up ? 'up' : 'down'}`}>{up ? '▲' : '▼'} {formatPercent(change)}</b>}
      </span>
      <small className="macro-card-id">{asset.symbol} · USD per troy ounce · open in explorer</small>
    </button>
  )
}

/** Gold and silver: stored daily COMEX futures bars, from the shared asset list. */
function Metals({ assets, loading, error }) {
  const metals = assets.filter((asset) => asset.asset_type === 'commodity')
  if (loading) return <section className="panel empty-panel">Loading gold and silver…</section>
  if (error) return <section className="panel empty-panel ix-error">Gold and silver could not be loaded: {error}</section>
  if (metals.length === 0) {
    return (
      <section className="panel empty-panel">
        No gold or silver history is stored yet. Add it with python src/data/update_equities.py (a dry run first;
        --apply to write).
      </section>
    )
  }
  return (
    <>
      <p className="macro-notice">
        Gold and silver are end-of-day COMEX front-month futures prices from Yahoo Finance (personal use), not spot
        prices, and never live. The newest day is stored only once Yahoo has finished updating it. Yahoo&apos;s silver
        series stays on the expiring contract until it expires, so some days trade very thinly (one price all day) and
        the price can jump slightly when it moves to the next contract.
      </p>
      <section className="macro-grid" aria-label="Gold and silver">
        {metals.map((asset) => <MetalCard key={asset.symbol} asset={asset} />)}
      </section>
    </>
  )
}

function History({ seriesId, range, onRange, releaseNote }) {
  const { data, loading, error } = useCommodityHistory(seriesId)
  const points = useMemo(() => (data ? toChartPoints(withinYears(data.observations, range)) : []), [data, range])

  if (loading) return <section className="panel empty-panel">Loading {seriesId}…</section>
  if (error) return <section className="panel empty-panel ix-error">{seriesId}: {error}</section>
  if (!data) return null

  const fetched = parseTimestamp(data.meta?.retrieved_at)
  return (
    <section className="panel macro-detail" aria-label={`${data.label} history`}>
      <div className="ix-head">
        <div className="min-w-0">
          <h2>{data.label} <span>{data.id}</span></h2>
          <p>Spot price · {data.currency} {data.unit}{data.units ? ` (${data.units})` : ''} · daily</p>
        </div>
        <div className="range-control" role="group" aria-label="Range">
          {RANGES.map((item) => (
            <button
              key={item.label}
              onClick={() => onRange(item.years)}
              className={item.years === range ? 'range-active' : ''}
              aria-pressed={item.years === range}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      <div className="ix-source">
        <DataTag status={tagFor(data)} />
        <span>
          EIA · latest price {formatObservationDate(data.latest?.date, 'Daily')}
          {fetched && ` · fetched ${fetchedFormat.format(fetched)} UTC`}
        </span>
        <span>{releaseNote}</span>
        {data.missing > 0 && (
          <span>{data.missing === 1 ? '1 date has' : `${data.missing} dates have`} no price and {data.missing === 1 ? 'is' : 'are'} shown as gaps</span>
        )}
        {data.meta?.notes?.map((note) => <span key={note} className="ix-warn">{note}</span>)}
      </div>
      <div className="ix-chart-wrap">
        <SeriesChart points={points} />
        {points.length === 0 && <div className="candle-overlay">EIA returned no prices for this range.</div>}
      </div>
      <p className="ix-footnote">Spot prices as reported by EIA, in US dollars per barrel, not adjusted for inflation.</p>
    </section>
  )
}

/** Commodities: gold and silver futures from the database, then WTI and Brent spot prices from EIA. */
export default function CommoditiesPage({ marketAssets = [], assetLoading = false, assetError = null }) {
  return (
    <div className="ix">
      <Metals assets={marketAssets} loading={assetLoading} error={assetError} />
      <Oil />
    </div>
  )
}

function Oil() {
  const { data, loading, error } = useCommodities()
  const [selected, setSelected] = useState('')
  const [range, setRange] = useState(1)

  if (loading) return <section className="panel empty-panel">Loading oil prices…</section>
  if (error) return <section className="panel empty-panel ix-error">Oil prices could not be loaded: {error}</section>

  if (!data.configured) {
    return (
      <section className="panel macro-setup">
        <h2>Oil prices are not configured</h2>
        <p>
          FinPulse reads WTI and Brent crude oil spot prices from the U.S. Energy Information Administration, which
          needs a free API key. Nothing is shown until one is set, rather than placeholder numbers.
        </p>
        <ol>
          <li>Register for a key at <a href="https://www.eia.gov/opendata/register.php" target="_blank" rel="noreferrer">eia.gov/opendata</a>.</li>
          <li>Add <code>EIA_API_KEY=your-key</code> to the <code>.env</code> file in the project folder (it is never committed).</li>
          <li>Restart the backend.</li>
        </ol>
      </section>
    )
  }

  const available = data.commodities.filter((item) => item.status !== 'unavailable')
  const current = selected || available[0]?.id || ''

  return (
    <>
      <p className="macro-notice">
        {data.citation} {data.release_note}{' '}
        <a href={data.source_url} target="_blank" rel="noreferrer">About EIA petroleum data</a>.
      </p>
      {available.length === 0 && (
        <section className="panel empty-panel ix-error">EIA is unavailable. {data.commodities[0]?.error}</section>
      )}
      <section className="macro-grid" aria-label="Commodities">
        {data.commodities.map((item) => (
          <Card key={item.id} item={item} active={item.id === current} onSelect={setSelected} />
        ))}
      </section>
      {current && <History seriesId={current} range={range} onRange={setRange} releaseNote={data.release_note} />}
    </>
  )
}
