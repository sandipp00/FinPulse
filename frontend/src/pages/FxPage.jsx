import { useMemo, useState } from 'react'
import DataTag from '../components/DataTag'
import SeriesChart from '../components/SeriesChart'
import { useFxHistory, useFxPairs } from '../hooks/useFx'
import { isCachedFallback, parseTimestamp } from '../lib/dataStatus'
import { describeRate, formatRate, rateDecimals, toRatePoints } from '../lib/fx'
import { formatPercent } from '../lib/format'
import { formatObservationDate, withinYears } from '../lib/macro'

const RANGES = [
  { label: '1Y', years: 1 },
  { label: '5Y', years: 5 },
  { label: '10Y', years: null },
]

const fetchedFormat = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })

const tagFor = (pair) => (pair.status === 'unavailable' ? 'unavailable' : isCachedFallback(pair.meta) ? 'cached' : 'historical')

function PairCard({ pair, active, onSelect }) {
  const available = pair.status !== 'unavailable'
  const up = pair.change_pct != null && pair.change_pct >= 0
  return (
    <button
      className={`macro-card ${active ? 'macro-card-active' : ''}`}
      onClick={() => onSelect(pair.pair)}
      disabled={!available}
      aria-pressed={active}
      title={available ? pair.method : pair.error}
    >
      <span className="macro-card-top">
        <span>{pair.derived ? 'Derived cross' : 'ECB reference'}</span>
        <DataTag status={tagFor(pair)} />
      </span>
      <strong className="macro-card-title">{pair.pair}</strong>
      <span className="macro-card-value num">{formatRate(pair.latest?.rate)}</span>
      <span className="macro-card-meta">
        {available ? (
          <>
            {formatObservationDate(pair.latest?.date, 'Daily')}
            {pair.change_pct != null && (
              <b className={`num ${up ? 'up' : 'down'}`}>{up ? '▲' : '▼'} {formatPercent(pair.change_pct)}</b>
            )}
          </>
        ) : (pair.error ?? 'Unavailable')}
      </span>
      <small className="macro-card-id">{pair.quote} per 1 {pair.base}</small>
    </button>
  )
}

function History({ pair, range, onRange }) {
  const { data, loading, error } = useFxHistory(pair)
  const points = useMemo(() => (data ? toRatePoints(withinYears(data.observations, range)) : []), [data, range])

  if (loading) return <section className="panel empty-panel">Loading {pair}…</section>
  if (error) return <section className="panel empty-panel ix-error">{pair}: {error}</section>
  if (!data) return null

  const fetched = parseTimestamp(data.meta?.retrieved_at)
  return (
    <section className="panel macro-detail" aria-label={`${pair} history`}>
      <div className="ix-head">
        <div className="min-w-0">
          <h2>{data.pair} <span>{describeRate(data.base, data.quote, data.latest?.rate)}</span></h2>
          <p>{data.method}</p>
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
          ECB · rate of {formatObservationDate(data.latest?.date, 'Daily')}, published around 16:00 CET
          {fetched && ` · fetched ${fetchedFormat.format(fetched)} UTC`}
        </span>
        {data.meta?.notes?.map((note) => <span key={note} className="ix-warn">{note}</span>)}
      </div>
      <div className="ix-chart-wrap">
        <SeriesChart points={points} precision={rateDecimals(data.latest?.rate ?? 1)} />
        {points.length === 0 && <div className="candle-overlay">No rates in this range.</div>}
      </div>
      <p className="ix-footnote">
        One rate per TARGET working day; weekends and holidays have none, and none is filled in.
        Reference rates are for information only and are not tradable quotes.
      </p>
    </section>
  )
}

/** FX: ECB euro reference rates, plus cross rates derived from them. */
export default function FxPage() {
  const { data, loading, error } = useFxPairs()
  const [selected, setSelected] = useState('')
  const [range, setRange] = useState(1)

  if (loading) return <section className="panel empty-panel">Loading FX rates…</section>
  if (error) return <section className="panel empty-panel ix-error">FX rates could not be loaded: {error}</section>

  const available = data.pairs.filter((pair) => pair.status !== 'unavailable')
  const current = selected || available[0]?.pair || ''

  return (
    <div className="ix">
      <p className="macro-notice">
        {data.notice} Pairs marked <b>Derived cross</b> are calculated by FinPulse from two ECB euro rates and are not
        published by the ECB. <a href={data.source_url} target="_blank" rel="noreferrer">About the ECB reference rates</a>.
      </p>
      {available.length === 0 && (
        <section className="panel empty-panel ix-error">The FX source is unavailable. {data.pairs[0]?.error}</section>
      )}
      <section className="macro-grid" aria-label="FX pairs">
        {data.pairs.map((pair) => (
          <PairCard key={pair.pair} pair={pair} active={pair.pair === current} onSelect={setSelected} />
        ))}
      </section>
      {current && <History pair={current} range={range} onRange={setRange} />}
    </div>
  )
}
