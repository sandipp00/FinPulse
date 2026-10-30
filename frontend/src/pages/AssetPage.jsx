import { useMemo, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, CandlestickChart } from 'lucide-react'
import AppLink from '../components/AppLink'
import DataTag from '../components/DataTag'
import ExplorerChart from '../components/ExplorerChart'
import LivePrice from '../components/LivePrice'
import NewsItem from '../components/NewsItem'
import SeriesChart from '../components/SeriesChart'
import { useAssetNews, useAssetQuery, useAssetRegistry } from '../hooks/useAsset'
import { useCommodities } from '../hooks/useCommodities'
import { useFxHistory, useFxPairs } from '../hooks/useFx'
import { useInstrumentHistory, useInstruments } from '../hooks/useInstruments'
import { useNow } from '../hooks/useNow'
import { CLASS_LABEL, chartInstrument, findAsset, groupAssets } from '../lib/asset'
import { describeSource, formatAsOfDate, parseTimestamp, tickStatus } from '../lib/dataStatus'
import { formatQuote, summarizeReturns, volumeUnit } from '../lib/explorer'
import { formatCompact, formatPercent, formatPrice, getAssetDetails } from '../lib/format'
import { formatRate, toRatePoints } from '../lib/fx'
import { formatObservationDate, withinYears } from '../lib/macro'
import { ROUTES } from '../lib/routes'

const INTERVAL_LABEL = { '1m': '1m', '15m': '15m', '1h': '1h', '1d': '1D' }
const CHART_BARS = 500
const timeFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'UTC',
})

const toneOf = (value) => (value == null ? '' : value >= 0 ? 'up' : 'down')

function Stat({ label, children, tone }) {
  return (
    <div className="ix-stat">
      <dt>{label}</dt>
      <dd className={`num ${tone ?? ''}`}>{children ?? '—'}</dd>
    </div>
  )
}

/** One column per asset class, its assets listed underneath. FX pairs show their code (EUR/USD). */
function Picker({ groups, current, onPick }) {
  return (
    <nav className="panel at-picker" aria-label="Assets">
      {groups.map((group) => (
        <div key={group.assetClass} className="at-picker-group" role="group" aria-label={group.label}>
          <span className="at-picker-label">{group.label}</span>
          <div className="at-picker-list">
            {group.assets.map((asset) => (
              <button
                key={asset.id}
                onClick={() => onPick(asset.id)}
                className={asset.id === current ? 'at-picker-active' : ''}
                aria-pressed={asset.id === current}
                title={asset.name}
              >
                {asset.asset_class === 'fx' ? asset.live : asset.name}
              </button>
            ))}
          </div>
        </div>
      ))}
    </nav>
  )
}

/** Name, the live price with its freshness, the change, and where the price comes from. */
function Header({ asset, tick, freshness, stored, instrument }) {
  const change = tick ? tick.change_pct_24h : stored?.daily_change_pct
  const window = tick ? (tick.change_window === '1d' ? 'since previous close' : '24h') : 'last stored day'
  const priceTime = tick?.time ? new Date(tick.time) : parseTimestamp(stored?.latest_timestamp)
  const symbol = asset.live ?? asset.stored
  return (
    <section className="panel at-header">
      <div className="min-w-0">
        <p className="at-kicker">{CLASS_LABEL[asset.asset_class]} · {[asset.live, asset.stored, asset.eia, asset.ecb].filter(Boolean).filter((s, i, all) => all.indexOf(s) === i).join(' · ')}</p>
        <h2 className="at-name">{asset.name}</h2>
        <p className="at-note">{asset.note}</p>
      </div>
      <div className="at-quote">
        <div className="at-price num">
          {tick ? <LivePrice tick={tick} /> : formatPrice(stored?.latest_price, symbol)}
          <DataTag status={tick ? freshness : stored ? 'historical' : 'unavailable'} />
        </div>
        {change != null && (
          <div className={`at-change num ${toneOf(change)}`}>
            {change >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
            {formatPercent(change)} <span>{window}</span>
          </div>
        )}
        <div className="at-time">
          {priceTime ? `${tick ? 'Price time' : 'Stored close'} ${timeFormat.format(priceTime)} UTC` : 'Waiting for the first price…'}
        </div>
        {instrument && (
          <AppLink href={`${ROUTES.explorer}?symbol=${encodeURIComponent(instrument.symbol)}`} className="at-link">
            <CandlestickChart size={13} /> Open in explorer
          </AppLink>
        )}
      </div>
    </section>
  )
}

function CandlesPanel({ instrument }) {
  const intervals = instrument.intervals
  const [chosen, setChosen] = useState(null)
  const interval = intervals.includes(chosen) ? chosen : (intervals.includes('1h') ? '1h' : intervals[0])
  const { data, loading, error } = useInstrumentHistory(instrument.symbol, interval, CHART_BARS)
  const candles = useMemo(() => data?.candles ?? [], [data])
  const summary = useMemo(() => summarizeReturns(candles), [candles])

  return (
    <section className="panel at-chart" aria-label="Price chart">
      <div className="ix-head">
        <div>
          <h2>{instrument.symbol} <span>{getAssetDetails(instrument.symbol).name}</span></h2>
          <p>{data ? describeSource(data.meta) : ' '}</p>
        </div>
        <div className="range-control" role="group" aria-label="Interval">
          {intervals.map((item) => (
            <button key={item} onClick={() => setChosen(item)} className={item === interval ? 'range-active' : ''} aria-pressed={item === interval}>
              {INTERVAL_LABEL[item] ?? item}
            </button>
          ))}
        </div>
      </div>
      <div className="ix-chart-wrap">
        <ExplorerChart
          candles={candles}
          showVolume={Boolean(volumeUnit(instrument))}
          comparison={null}
          intraday={interval !== '1d'}
          asLine={instrument.asset_class === 'fx' && interval === '1m'}
        />
        {loading && <div className="candle-overlay">Loading {instrument.symbol}…</div>}
        {error && <div className="candle-overlay candle-error">{error}</div>}
      </div>
      {summary && (
        <dl className="ix-stats">
          <Stat label={`Return over these ${summary.bars} bars`} tone={toneOf(summary.periodReturnPct)}>{formatPercent(summary.periodReturnPct)}</Stat>
          <Stat label="High in chart">{formatQuote(summary.high)}</Stat>
          <Stat label="Low in chart">{formatQuote(summary.low)}</Stat>
          <Stat label="Best / worst bar">{formatPercent(summary.bestBarPct)} / {formatPercent(summary.worstBarPct)}</Stat>
        </dl>
      )}
    </section>
  )
}

function EcbPanel({ pair }) {
  const { data, loading, error } = useFxHistory(pair)
  const points = useMemo(() => (data ? toRatePoints(withinYears(data.observations, 1)) : []), [data])
  return (
    <section className="panel at-chart" aria-label="ECB reference rate chart">
      <div className="ix-head">
        <div>
          <h2>{pair} <span>ECB reference rate, last year</span></h2>
          <p>Daily, published around 16:00 CET. Intraday history is not available for FX.</p>
        </div>
      </div>
      <div className="ix-chart-wrap">
        <SeriesChart points={points} />
        {loading && <div className="candle-overlay">Loading {pair}…</div>}
        {error && <div className="candle-overlay candle-error">{error}</div>}
      </div>
    </section>
  )
}

function KeyFigures({ asset, tick, stored, instrument }) {
  return (
    <section className="panel at-figures" aria-label="Key figures">
      <h3 className="at-section-title">Key figures</h3>
      <dl className="ix-stats">
        {tick?.previous_close != null && <Stat label="Previous close">{formatQuote(tick.previous_close, getAssetDetails(asset.live).currency)}</Stat>}
        {tick?.high_24h != null && (
          <>
            <Stat label="24h high">{formatPrice(tick.high_24h, asset.live)}</Stat>
            <Stat label="24h low">{formatPrice(tick.low_24h, asset.live)}</Stat>
            <Stat label={`24h volume${instrument && volumeUnit(instrument) ? ` (${volumeUnit(instrument)})` : ''}`}>{formatCompact(tick.volume_24h)}</Stat>
          </>
        )}
        {stored && (
          <>
            <Stat label="Total return, stored history" tone={toneOf(stored.total_return_pct)}>{formatPercent(stored.total_return_pct)}</Stat>
            <Stat label="Volatility (annualized)">{formatPercent(stored.annualized_volatility_pct)}</Stat>
            <Stat label="Max drawdown" tone="down">{formatPercent(stored.max_drawdown_pct)}</Stat>
            <Stat label="Sharpe ratio">{stored.sharpe_ratio?.toFixed(2)}</Stat>
            <Stat label="Stored daily history">
              {formatAsOfDate(stored.first_date, { withYear: true })} to {formatAsOfDate(stored.last_date, { withYear: true })}
            </Stat>
          </>
        )}
      </dl>
    </section>
  )
}

function EiaReference({ series }) {
  const { data } = useCommodities()
  const item = data?.commodities?.find((c) => c.id === series)
  if (!item) return null
  return (
    <li className="at-related-row">
      <span>EIA spot ({series})</span>
      <b className="num">{formatQuote(item.latest?.value, 'USD')}</b>
      <span>{formatObservationDate(item.latest?.date, 'Daily')}</span>
      <DataTag status={item.status === 'unavailable' ? 'unavailable' : 'historical'} />
    </li>
  )
}

function EcbReference({ pair }) {
  const { data } = useFxPairs()
  const item = data?.pairs?.find((p) => p.pair === pair)
  if (!item) return null
  return (
    <li className="at-related-row">
      <span>{item.derived ? 'ECB-derived cross' : 'ECB reference'}</span>
      <b className="num">{formatRate(item.latest?.rate)}</b>
      <span>{formatObservationDate(item.latest?.date, 'Daily')}</span>
      <DataTag status={item.status === 'unavailable' ? 'unavailable' : 'historical'} />
    </li>
  )
}

/** Other prices for the same asset: stored daily close, EIA and ECB references. */
function Related({ asset, stored, hasTick }) {
  const showStored = stored && (asset.stored !== asset.live || !hasTick)
  if (!showStored && !asset.eia && !asset.ecb) return null
  return (
    <section className="panel at-related" aria-label="Related prices">
      <h3 className="at-section-title">Reference prices</h3>
      <ul>
        {showStored && (
          <li className="at-related-row">
            <span>{asset.stored} daily close</span>
            <b className="num">{formatPrice(stored.latest_price, asset.stored)}</b>
            <span>{formatAsOfDate(stored.latest_timestamp, { withYear: true })}</span>
            <DataTag status="historical" />
          </li>
        )}
        {asset.eia && <EiaReference series={asset.eia} />}
        {asset.ecb && <EcbReference pair={asset.ecb} />}
      </ul>
    </section>
  )
}

function NewsPanel({ asset }) {
  const { data, loading, error } = useAssetNews(asset.has_news ? asset.id : '')
  const now = useNow(30_000)
  return (
    <section className="panel at-news" aria-label={`${asset.name} news`}>
      <div className="at-news-head">
        <h3 className="at-section-title">Latest news</h3>
        {data && <span>Refreshed every {Math.round(data.refresh_seconds / 60)} min</span>}
      </div>
      {!asset.has_news && <p className="at-empty">No news feed for {asset.name}, by choice.</p>}
      {asset.has_news && loading && <p className="at-empty">Loading headlines…</p>}
      {error && <p className="at-empty ix-error">{data ? 'Refresh failed; showing the last headlines. ' : ''}{error}</p>}
      {data && data.items.length === 0 && <p className="at-empty">No recent headlines name {asset.name}.</p>}
      {data && data.items.length > 0 && (
        <ul className="news-list">
          {data.items.map((item) => <NewsItem key={item.id} item={item} loadedAt={now} />)}
        </ul>
      )}
      {data && (
        <p className="at-sources">
          {data.sources.map((s) => `${s.name}: ${s.status === 'ok' ? `${s.count} headline${s.count === 1 ? '' : 's'}` : s.status}`).join(' · ')}.
          {' '}{data.policy}
        </p>
      )}
    </section>
  )
}

/**
 * The asset terminal: everything about one asset on one screen. Live price and
 * freshness, a chart, key figures, reference prices and the asset's latest news.
 */
export default function AssetPage({ ticks = {}, marketStatus = {}, marketAssets = [] }) {
  const registry = useAssetRegistry()
  const { instruments } = useInstruments()
  const [query, setQuery] = useAssetQuery()
  const now = useNow(5000)

  const groups = useMemo(() => groupAssets(registry.assets), [registry.assets])
  const asset = findAsset(registry.assets, query) ?? registry.assets[0] ?? null

  if (registry.loading) return <section className="panel empty-panel">Loading assets…</section>
  if (registry.error) return <section className="panel empty-panel ix-error">Assets could not be loaded: {registry.error}</section>
  if (!asset) return <section className="panel empty-panel">No assets are configured.</section>

  const tick = asset.live ? ticks[asset.live] : null
  const stored = asset.stored ? marketAssets.find((a) => a.symbol === asset.stored) : null
  const instrument = chartInstrument(asset, instruments)

  return (
    <div className="ix at">
      <Picker groups={groups} current={asset.id} onPick={setQuery} />
      <Header asset={asset} tick={tick} freshness={tickStatus(tick, marketStatus, now)} stored={stored} instrument={instrument} />
      <div className="at-grid">
        <div className="at-main">
          {instrument
            ? <CandlesPanel key={instrument.symbol} instrument={instrument} />
            : asset.ecb && <EcbPanel pair={asset.ecb} />}
          <KeyFigures asset={asset} tick={tick} stored={stored} instrument={instrument} />
          <Related asset={asset} stored={stored} hasTick={Boolean(tick)} />
        </div>
        <NewsPanel key={asset.id} asset={asset} />
      </div>
    </div>
  )
}
