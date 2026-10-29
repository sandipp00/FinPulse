import { useMemo, useState } from 'react'
import DataTag from '../components/DataTag'
import MacroChart from '../components/MacroChart'
import { useMacroDetail, useMacroSeries } from '../hooks/useMacro'
import { isCachedFallback, parseTimestamp } from '../lib/dataStatus'
import {
  CATEGORY_LABEL,
  formatMacroChange,
  formatMacroValue,
  formatObservationDate,
  toChartPoints,
  withinYears,
} from '../lib/macro'

const RANGES = [
  { label: '1Y', years: 1 },
  { label: '5Y', years: 5 },
  { label: '10Y', years: null },
]

const updatedFormat = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
const fetchedFormat = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })

/** FRED's required notice and terms link; shown whenever FRED data could be on screen. */
function FredNotice({ notice, termsUrl }) {
  return (
    <p className="macro-notice">
      {notice} Data via <a href="https://fred.stlouisfed.org/" target="_blank" rel="noreferrer">FRED</a>;
      using it here means accepting the{' '}
      <a href={termsUrl} target="_blank" rel="noreferrer">FRED® API Terms of Use</a>.
    </p>
  )
}

function SeriesCard({ series, active, onSelect }) {
  const available = series.status !== 'unavailable'
  const positive = series.change != null && series.change >= 0
  return (
    <button
      className={`macro-card ${active ? 'macro-card-active' : ''}`}
      onClick={() => onSelect(series.id)}
      disabled={!available}
      aria-pressed={active}
      title={available ? series.title : series.error ?? 'Unavailable'}
    >
      <span className="macro-card-top">
        <span>{CATEGORY_LABEL[series.category] ?? series.category}</span>
        <DataTag status={available ? (isCachedFallback(series.meta) ? 'cached' : 'historical') : 'unavailable'} />
      </span>
      <strong className="macro-card-title">{series.label}</strong>
      <span className="macro-card-value num">{formatMacroValue(series.latest?.value, series.units_short)}</span>
      <span className="macro-card-meta">
        {available ? (
          <>
            {formatObservationDate(series.latest?.date, series.frequency)}
            {series.change != null && (
              <b className={`num ${positive ? 'up' : 'down'}`}>
                {positive ? '▲' : '▼'} {formatMacroChange(series.change, series.units_short)}
              </b>
            )}
          </>
        ) : (series.error ?? 'Unavailable')}
      </span>
      <small className="macro-card-id">{series.id}{series.seasonal_adjustment ? ` · ${series.seasonal_adjustment}` : ''}</small>
    </button>
  )
}

function Detail({ seriesId, range, onRange }) {
  const { data, loading, error } = useMacroDetail(seriesId)
  const points = useMemo(
    () => (data ? toChartPoints(withinYears(data.observations, range)) : []),
    [data, range],
  )

  if (loading) return <section className="panel empty-panel">Loading {seriesId}…</section>
  if (error) return <section className="panel empty-panel ix-error">{seriesId}: {error}</section>
  if (!data) return null

  const percent = (data.units_short ?? '').includes('%')
  const updated = parseTimestamp(data.last_updated)
  const meta = data.meta
  const fetched = parseTimestamp(meta?.retrieved_at)

  return (
    <section className="panel macro-detail" aria-label={`${data.title} chart`}>
      <div className="ix-head">
        <div className="min-w-0">
          <h2>{data.title} <span>{data.id}</span></h2>
          <p>{data.units} · {data.frequency}{data.seasonal_adjustment ? ` · ${data.seasonal_adjustment}` : ''}</p>
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
        <DataTag status={isCachedFallback(meta) ? 'cached' : 'historical'} />
        <span>
          FRED · latest observation {formatObservationDate(data.latest?.date, data.frequency)}
          {updated && ` · updated by the source ${updatedFormat.format(updated)}`}
          {fetched && ` · fetched ${fetchedFormat.format(fetched)} UTC`}
        </span>
        {data.missing > 0 && (
          <span>{data.missing === 1 ? '1 date has' : `${data.missing} dates have`} no value and {data.missing === 1 ? 'is' : 'are'} shown as gaps</span>
        )}
        {meta?.notes?.map((note) => <span key={note} className="ix-warn">{note}</span>)}
      </div>

      <div className="ix-chart-wrap">
        <MacroChart points={points} percent={percent} />
        {points.length === 0 && <div className="candle-overlay">FRED returned no observations for this range.</div>}
      </div>
      <p className="ix-footnote">
        Values as published; past values can be revised by the source. Shown without seasonal or inflation adjustment
        beyond what the series itself states.
      </p>
    </section>
  )
}

/** US macro series from FRED: latest values, then a chart of the selected one. */
export default function MacroPage() {
  const { data, loading, error } = useMacroSeries()
  const [selected, setSelected] = useState('')
  const [range, setRange] = useState(5)

  if (loading) return <section className="panel empty-panel">Loading macro series…</section>
  if (error) return <section className="panel empty-panel ix-error">Macro data could not be loaded: {error}</section>

  if (!data.configured) {
    return (
      <section className="panel macro-setup">
        <h2>Macro data is not configured</h2>
        <p>
          FinPulse reads US macroeconomic series from FRED, which needs a free API key. Nothing is shown until
          one is set, rather than placeholder numbers.
        </p>
        <ol>
          <li>Get a key at <a href="https://fred.stlouisfed.org/docs/api/api_key.html" target="_blank" rel="noreferrer">fred.stlouisfed.org</a>.</li>
          <li>Add <code>FRED_API_KEY=your-key</code> to the <code>.env</code> file in the project folder (it is never committed).</li>
          <li>Restart the backend.</li>
        </ol>
        <p className="macro-setup-list">Series that will appear: {data.series.map((s) => s.id).join(', ')}.</p>
      </section>
    )
  }

  const available = data.series.filter((s) => s.status !== 'unavailable')
  const current = selected || available[0]?.id || ''

  return (
    <div className="ix">
      <FredNotice notice={data.notice} termsUrl={data.terms_url} />
      {available.length === 0 && (
        <section className="panel empty-panel ix-error">FRED did not return any series. {data.series[0]?.error}</section>
      )}
      <section className="macro-grid" aria-label="Macro series">
        {data.series.map((series) => (
          <SeriesCard key={series.id} series={series} active={series.id === current} onSelect={setSelected} />
        ))}
      </section>
      {current && <Detail seriesId={current} range={range} onRange={setRange} />}
    </div>
  )
}
