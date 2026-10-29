import { useMemo, useState } from 'react'
import DataTag from '../components/DataTag'
import SeriesChart from '../components/SeriesChart'
import { useCommodities, useCommodityHistory } from '../hooks/useCommodities'
import { isCachedFallback, parseTimestamp } from '../lib/dataStatus'
import { formatQuote } from '../lib/explorer'
import { formatPercent } from '../lib/format'
import { formatObservationDate, toChartPoints, withinYears } from '../lib/macro'

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

/** Commodities: WTI and Brent crude oil spot prices from EIA. */
export default function CommoditiesPage() {
  const { data, loading, error } = useCommodities()
  const [selected, setSelected] = useState('')
  const [range, setRange] = useState(1)

  if (loading) return <section className="panel empty-panel">Loading commodity prices…</section>
  if (error) return <section className="panel empty-panel ix-error">Commodity prices could not be loaded: {error}</section>

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
        <p className="macro-setup-list">{data.not_covered}</p>
      </section>
    )
  }

  const available = data.commodities.filter((item) => item.status !== 'unavailable')
  const current = selected || available[0]?.id || ''

  return (
    <div className="ix">
      <p className="macro-notice">
        {data.citation} {data.release_note} {data.not_covered}{' '}
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
    </div>
  )
}
