import { useEffect, useMemo } from 'react'
import { RefreshCw } from 'lucide-react'
import DataTag from '../components/DataTag'
import ExplorerChart from '../components/ExplorerChart'
import InstrumentSearch from '../components/InstrumentSearch'
import RelativePanel from '../components/RelativePanel'
import { useExplorerQuery } from '../hooks/useExplorerQuery'
import { useInstrumentHistory, useInstruments } from '../hooks/useInstruments'
import { describeSource, formatAge, isCachedFallback } from '../lib/dataStatus'
import {
  alignForComparison,
  formatBarTime,
  formatQuote,
  limitLabel,
  limitOptions,
  resolveExplorerState,
  sourceFor,
  summarizeReturns,
  volumeUnit,
} from '../lib/explorer'
import { formatCompact, formatPercent, getAssetDetails } from '../lib/format'

const CLASS_LABEL = { crypto: 'Crypto', stock: 'Stock', index: 'Index', commodity: 'Commodity', fx: 'FX' }
const INTERVAL_LABEL = { '1m': '1 minute', '15m': '15 minutes', '1h': '1 hour', '1d': '1 day' }
const ALL_INTERVALS = ['1m', '15m', '1h', '1d']

function Stat({ label, children, tone }) {
  return (
    <div className="ix-stat">
      <dt>{label}</dt>
      <dd className={`num ${tone ?? ''}`}>{children}</dd>
    </div>
  )
}

const toneOf = (value) => (value == null ? '' : value >= 0 ? 'up' : 'down')

/** Which tag the series gets: a kept response is CACHED, everything else is past bars (HIST). */
const tagFor = (meta) => (isCachedFallback(meta) ? 'cached' : 'historical')

function SourceLine({ data }) {
  if (!data) return null
  const { meta } = data
  return (
    <div className="ix-source">
      <DataTag status={tagFor(meta)} />
      <span>{data.source === 'database' ? 'Stored daily history · ' : ''}{describeSource(meta)}</span>
      {isCachedFallback(meta) && <span className="ix-warn">Fetched {formatAge((meta.cache_age_seconds ?? 0) * 1000)}; the exchange is not answering.</span>}
      {meta.notes?.map((note) => <span key={note} className="ix-warn">{note}</span>)}
    </div>
  )
}

/**
 * Pick any supported instrument and inspect its history: candles and volume,
 * return figures, and a rebased comparison against a second instrument.
 */
export default function ExplorerPage() {
  const { instruments, loading: listLoading, error: listError } = useInstruments()
  const [query, setQuery] = useExplorerQuery()

  const state = useMemo(() => resolveExplorerState(query, instruments), [query, instruments])

  // Write the corrected state back, so the address bar always describes what is shown.
  useEffect(() => {
    if (!state) return
    const { symbol, interval, limit, compare } = state
    if (symbol !== query.symbol || interval !== query.interval || limit !== query.limit || compare !== query.compare) {
      setQuery({ symbol, interval, limit, compare })
    }
  }, [state, query, setQuery])

  const primary = useInstrumentHistory(state?.symbol ?? '', state?.interval, state?.limit)
  const other = useInstrumentHistory(state?.compare ?? '', state?.interval, state?.limit)

  const candles = useMemo(() => primary.data?.candles ?? [], [primary.data])
  const summary = useMemo(() => summarizeReturns(candles), [candles])
  const comparison = useMemo(() => {
    if (!state?.compare || !other.data) return null
    return alignForComparison(candles, other.data.candles, state.interval)
  }, [state, candles, other.data])

  if (listLoading) return <section className="panel empty-panel">Loading supported instruments…</section>
  if (listError) return <section className="panel empty-panel ix-error">Instruments could not be loaded: {listError}</section>
  if (!state) return <section className="panel empty-panel">No instruments are available. Load stored history or enable the live feed.</section>

  const { instrument, interval, limit } = state
  const details = getAssetDetails(instrument.symbol)
  const currency = primary.data?.currency ?? instrument.currency
  const unitText = [currency ? `Quoted in ${currency}` : 'Currency not reported', instrument.unit].join(' · ')
  const volUnit = volumeUnit(instrument)
  const showVolume = Boolean(summary?.volumeReported)
  const compareInstrument = instruments.find((item) => item.symbol === state.compare)
  const compareCurrency = other.data?.currency ?? compareInstrument?.currency
  const comparing = Boolean(state.compare)
  const comparisonReady = comparing && comparison && comparison.points.length > 0

  const compareDisabled = (item) => {
    if (item.symbol === instrument.symbol) return 'Already selected'
    if (!item.intervals.includes(interval)) return `No ${INTERVAL_LABEL[interval]} bars`
    return null
  }

  return (
    <div className="ix">
      <section className="panel ix-controls" aria-label="Explorer controls">
        <InstrumentSearch
          label="Instrument"
          instruments={instruments}
          value={instrument.symbol}
          onChange={(symbol) => setQuery({ symbol })}
        />
        <div className="ix-control">
          <span className="ix-search-label">Interval</span>
          <div className="range-control" role="group" aria-label="Interval">
            {ALL_INTERVALS.map((item) => {
              const supported = instrument.intervals.includes(item)
              return (
                <button
                  key={item}
                  onClick={() => setQuery({ interval: item })}
                  className={item === interval ? 'range-active' : ''}
                  disabled={!supported}
                  aria-pressed={item === interval}
                  title={supported ? INTERVAL_LABEL[item] : `${instrument.symbol} has daily history only`}
                >
                  {item}
                </button>
              )
            })}
          </div>
        </div>
        <div className="ix-control">
          <span className="ix-search-label">Bars</span>
          <div className="range-control" role="group" aria-label="Number of bars">
            {limitOptions(sourceFor(instrument)).map((item) => (
              <button
                key={item}
                onClick={() => setQuery({ limit: item })}
                className={item === limit ? 'range-active' : ''}
                aria-pressed={item === limit}
              >
                {limitLabel(item)}
              </button>
            ))}
          </div>
        </div>
        <InstrumentSearch
          label="Compare with"
          instruments={instruments}
          value={state.compare}
          onChange={(compare) => setQuery({ compare })}
          disabledReason={compareDisabled}
          allowNone
        />
      </section>

      <section className="panel ix-main">
        <div className="ix-head">
          <div className="min-w-0">
            <h2>{instrument.symbol} <span>{details.name}</span></h2>
            <p>{CLASS_LABEL[instrument.asset_class]} · {unitText} · {INTERVAL_LABEL[interval]} bars · times in UTC</p>
          </div>
          {summary && (
            <div className="ix-last">
              <strong className="num">{formatQuote(summary.lastClose, currency)}</strong>
              <span className={`num ${toneOf(summary.periodReturnPct)}`}>
                {summary.periodReturnPct >= 0 ? '▲' : '▼'} {formatPercent(summary.periodReturnPct)} over window
              </span>
            </div>
          )}
        </div>
        <SourceLine data={primary.data} />

        {comparing && (
          <div className="ix-legend">
            <span><i style={{ background: '#34D399' }} />{instrument.symbol}
              {comparisonReady && <b className={`num ${toneOf(comparison.primaryReturnPct)}`}>{formatPercent(comparison.primaryReturnPct)}</b>}
            </span>
            <span><i style={{ background: '#818CF8' }} />{state.compare}
              {comparisonReady && <b className={`num ${toneOf(comparison.otherReturnPct)}`}>{formatPercent(comparison.otherReturnPct)}</b>}
            </span>
            <span className="ix-legend-note">
              {comparisonReady
                ? `Both rebased to 100 on ${formatBarTime(comparison.points[0].time, interval)}; ${comparison.shared} shared bars.`
                : 'Waiting for both series…'}
              {comparisonReady && currency && compareCurrency && currency !== compareCurrency
                && ` Quoted in ${currency} and ${compareCurrency}; no currency conversion is applied.`}
            </span>
          </div>
        )}

        <div className="ix-chart-wrap">
          <ExplorerChart
            candles={candles}
            showVolume={showVolume}
            comparison={comparisonReady ? comparison : null}
            intraday={interval !== '1d'}
          />
          {primary.loading && <div className="candle-overlay">Loading {instrument.symbol} history…</div>}
          {primary.error && (
            <div className="candle-overlay candle-error">
              <span>{primary.error}</span>
              <button onClick={primary.reload}><RefreshCw size={13} /> Retry</button>
            </div>
          )}
          {!primary.loading && !primary.error && candles.length === 0 && (
            <div className="candle-overlay">The source returned no bars for this selection.</div>
          )}
          {comparing && other.error && (
            <div className="candle-overlay candle-error">
              <span>{state.compare}: {other.error}</span>
              <button onClick={other.reload}><RefreshCw size={13} /> Retry</button>
            </div>
          )}
          {comparing && comparison && !comparisonReady && !other.loading && (
            <div className="candle-overlay">{instrument.symbol} and {state.compare} share fewer than two bars in this window.</div>
          )}
        </div>
        {comparing && <SourceLine data={other.data} />}
      </section>

      {summary && (
        <section className="panel ix-returns" aria-label="Returns and volume">
          <h2>Returns and volume <span>over the {summary.bars} bars shown</span></h2>
          <dl className="ix-stats">
            <Stat label="From">{formatBarTime(summary.firstTime, interval)}</Stat>
            <Stat label="To">{formatBarTime(summary.lastTime, interval)}</Stat>
            <Stat label="First close">{formatQuote(summary.firstClose, currency)}</Stat>
            <Stat label="Last close">{formatQuote(summary.lastClose, currency)}</Stat>
            <Stat label="Simple return" tone={toneOf(summary.periodReturnPct)}>{formatPercent(summary.periodReturnPct)}</Stat>
            <Stat label="Log return" tone={toneOf(summary.logReturnPct)}>{formatPercent(summary.logReturnPct)}</Stat>
            <Stat label="Best bar" tone="up">{formatPercent(summary.bestBarPct)}</Stat>
            <Stat label="Worst bar" tone="down">{formatPercent(summary.worstBarPct)}</Stat>
            <Stat label="Bar volatility">{summary.barVolatilityPct == null ? '—' : `${summary.barVolatilityPct.toFixed(2)}%`}</Stat>
            <Stat label="High / low">{formatQuote(summary.high, currency)} / {formatQuote(summary.low, currency)}</Stat>
            <Stat label="Average volume">
              {summary.volumeReported ? `${formatCompact(summary.averageVolume)}${volUnit ? ` ${volUnit}` : ''}` : 'Not reported by source'}
            </Stat>
          </dl>
          <p className="ix-footnote">
            Returns use closing prices only, with no fees, dividends or currency conversion.
            Bar volatility is the standard deviation of bar-to-bar returns, not annualized.
          </p>
        </section>
      )}

      {comparing && interval === '1d' && <RelativePanel symbol={instrument.symbol} benchmark={state.compare} />}
      {comparing && interval !== '1d' && (
        <section className="panel empty-panel">Beta, correlation and the other relative statistics use daily bars. Switch to 1d to see them.</section>
      )}
    </div>
  )
}
