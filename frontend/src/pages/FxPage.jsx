import { useEffect, useMemo, useState } from 'react'
import AppLink from '../components/AppLink'
import DataTag from '../components/DataTag'
import ExplorerChart from '../components/ExplorerChart'
import LivePrice from '../components/LivePrice'
import SeriesChart from '../components/SeriesChart'
import { useFxHistory, useFxPairs } from '../hooks/useFx'
import { useInstrumentHistory } from '../hooks/useInstruments'
import { useNow } from '../hooks/useNow'
import { assetHref } from '../lib/asset'
import { describeSource, isCachedFallback, parseTimestamp, tickStatus } from '../lib/dataStatus'
import { summarizeReturns } from '../lib/explorer'
import { describeRate, formatRate, rateDecimals, toRatePoints, withLiveTick } from '../lib/fx'
import { formatPercent } from '../lib/format'
import { formatObservationDate, withinYears } from '../lib/macro'

const RANGES = [
  { label: '1Y', years: 1 },
  { label: '5Y', years: 5 },
  { label: '10Y', years: null },
]

const fetchedFormat = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })

const tagFor = (pair) => (pair.status === 'unavailable' ? 'unavailable' : isCachedFallback(pair.meta) ? 'cached' : 'historical')

const INTERVAL_LABEL = { '1m': '1m', '15m': '15m', '1h': '1h', '1d': '1D' }
const LIVE_BARS = 500
// Intraday candles are re-fetched this often; the newest bar also follows each live tick.
const REFRESH_MS = 15_000

/** One pair: the live Yahoo rate as the headline, the ECB reference rate underneath. */
function PairCard({ symbol, ecb, active, onSelect, tick, liveStatus }) {
  const change = tick?.change_pct_24h
  const up = change != null && change >= 0
  return (
    <button
      className={`macro-card ${active ? 'macro-card-active' : ''}`}
      onClick={() => onSelect(symbol)}
      aria-pressed={active}
      title={ecb?.method ?? symbol}
    >
      <span className="macro-card-top">
        <span>Live · Yahoo Finance</span>
        <DataTag status={liveStatus} />
      </span>
      <strong className="macro-card-title">{symbol}</strong>
      <span className="macro-card-value num">{tick ? <LivePrice tick={tick} /> : '—'}</span>
      <span className="macro-card-meta">
        {tick ? 'Since previous close' : 'Waiting for the first quote…'}
        {change != null && <b className={`num ${up ? 'up' : 'down'}`}>{up ? '▲' : '▼'} {formatPercent(change)}</b>}
      </span>
      {ecb?.latest && (
        <span className="macro-card-meta">
          <span>{ecb.derived ? 'ECB cross' : 'ECB'} <span className="num">{formatRate(ecb.latest.rate)}</span></span>
          <span>{formatObservationDate(ecb.latest.date, 'Daily')}</span>
        </span>
      )}
      <small className="macro-card-id">{quoteOf(symbol)} per 1 {baseOf(symbol)}</small>
    </button>
  )
}

const baseOf = (symbol) => symbol.split('/')[0]
const quoteOf = (symbol) => symbol.split('/')[1]

function LiveChart({ symbol, tick, tag }) {
  const [interval, setInterval_] = useState('15m')
  const { data, loading, error, reload } = useInstrumentHistory(symbol, interval, LIVE_BARS)

  useEffect(() => {
    if (interval === '1d') return undefined
    const timer = setInterval(reload, REFRESH_MS)
    return () => clearInterval(timer)
  }, [interval, reload])

  const candles = useMemo(() => withLiveTick(data?.candles ?? [], tick), [data, tick])
  const summary = useMemo(() => summarizeReturns(candles), [candles])
  const decimals = rateDecimals(tick?.price ?? candles.at(-1)?.close ?? 1)

  return (
    <section className="panel macro-detail" aria-label={`${symbol} live chart`}>
      <div className="ix-head">
        <div className="min-w-0">
          <h2>{symbol} <span>{tick ? describeRate(baseOf(symbol), quoteOf(symbol), tick.price) : 'live'}</span></h2>
          <p>Live Yahoo Finance quotes; the newest bar is still forming. {interval === '1d' ? '' : 'Updates every 15 seconds.'}</p>
        </div>
        <div className="range-control" role="group" aria-label="Interval">
          {Object.keys(INTERVAL_LABEL).map((item) => (
            <button key={item} onClick={() => setInterval_(item)} className={item === interval ? 'range-active' : ''} aria-pressed={item === interval}>
              {INTERVAL_LABEL[item]}
            </button>
          ))}
        </div>
      </div>
      <div className="ix-source">
        <DataTag status={tag} />
        <span>{data ? describeSource(data.meta) : 'Loading…'}</span>
        {data?.meta?.notes?.map((note) => <span key={note} className="ix-warn">{note}</span>)}
      </div>
      <div className="ix-chart-wrap">
        {/* Yahoo's 1-minute FX bars are single prices, so they are drawn as a line. */}
        <ExplorerChart candles={candles} showVolume={false} comparison={null} intraday={interval !== '1d'} asLine={interval === '1m'} />
        {loading && <div className="candle-overlay">Loading {symbol}…</div>}
        {error && <div className="candle-overlay candle-error">{error}</div>}
      </div>
      {summary && (
        <dl className="ix-stats">
          <div className="ix-stat"><dt>Change over these {summary.bars} bars</dt><dd className={`num ${summary.periodReturnPct >= 0 ? 'up' : 'down'}`}>{formatPercent(summary.periodReturnPct, 3)}</dd></div>
          <div className="ix-stat"><dt>High in chart</dt><dd className="num">{summary.high.toFixed(decimals)}</dd></div>
          <div className="ix-stat"><dt>Low in chart</dt><dd className="num">{summary.low.toFixed(decimals)}</dd></div>
          {tick?.previous_close != null && (
            <div className="ix-stat"><dt>Previous close</dt><dd className="num">{tick.previous_close.toFixed(decimals)}</dd></div>
          )}
        </dl>
      )}
      <p className="ix-footnote">
        Yahoo Finance quotes are indicative, for personal use, and are not dealing prices. FX trades around the clock on
        weekdays; at weekends the last Friday quote stays.
      </p>
    </section>
  )
}

/** The ECB daily reference series, kept as the long-run official reference. */
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
          <h2>{data.pair} <span>ECB reference rate history</span></h2>
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

// The pairs the page shows, in order; their live quotes come from the Yahoo poller.
const PAIRS = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/INR', 'EUR/GBP', 'EUR/JPY', 'EUR/INR']

/** FX: live Yahoo quotes and intraday charts for every pair, with the ECB reference rates alongside. */
export default function FxPage({ ticks = {}, marketStatus = {} }) {
  const { data, error } = useFxPairs()
  const now = useNow(5000)
  const [selected, setSelected] = useState(PAIRS[0])
  const [range, setRange] = useState(1)
  const ecbByPair = useMemo(() => Object.fromEntries((data?.pairs ?? []).map((pair) => [pair.pair, pair])), [data])

  return (
    <div className="ix">
      <p className="macro-notice">
        Every rate here is live: near-real-time quotes from Yahoo Finance (personal use), refreshed every 15 seconds and
        tagged <b>LIVE</b>, <b>DELAYED</b> or <b>STALE</b>. Each card also shows the European Central Bank&apos;s daily
        reference rate; pairs marked <b>ECB cross</b> are calculated by FinPulse from two ECB euro rates.
        {data?.source_url && <>{' '}<a href={data.source_url} target="_blank" rel="noreferrer">About the ECB reference rates</a>.</>}
        {error && <span className="ix-warn"> The ECB rates could not be loaded: {error}</span>}
      </p>
      <section className="macro-grid" aria-label="FX pairs">
        {PAIRS.map((symbol) => (
          <PairCard
            key={symbol}
            symbol={symbol}
            ecb={ecbByPair[symbol]}
            active={symbol === selected}
            onSelect={setSelected}
            tick={ticks[symbol]}
            liveStatus={tickStatus(ticks[symbol], marketStatus, now)}
          />
        ))}
      </section>
      <div className="fx-asset-link">
        <AppLink href={assetHref(selected)}>Open {selected} in the asset terminal (with news) →</AppLink>
      </div>
      <LiveChart key={selected} symbol={selected} tick={ticks[selected]} tag={tickStatus(ticks[selected], marketStatus, now)} />
      {ecbByPair[selected] && <History pair={selected} range={range} onRange={setRange} />}
    </div>
  )
}
