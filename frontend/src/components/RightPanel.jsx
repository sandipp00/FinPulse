import { memo } from 'react'
import { ArrowDownRight, ArrowUpRight, LineChart } from 'lucide-react'
import { useNow } from '../hooks/useNow'
import { formatAge, formatAsOfDate, parseTimestamp, storedStatus, tickStatus } from '../lib/dataStatus'
import { formatCompact, formatPercent, formatPrice } from '../lib/format'
import DataTag from './DataTag'
import LivePrice from './LivePrice'

function Change({ value, suffix }) {
  if (value == null || !Number.isFinite(Number(value))) return <span className="rp-change">—</span>
  const positive = Number(value) >= 0
  return (
    <span className={`rp-change ${positive ? 'up' : 'down'}`}>
      {positive ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}
      {formatPercent(value)}{suffix}
    </span>
  )
}

function Field({ label, children }) {
  return (
    <div className="rp-field">
      <dt>{label}</dt>
      <dd className="num">{children}</dd>
    </div>
  )
}

const exchangeTime = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })

function Details({ asset, tick, freshness, now, onOpenChart }) {
  const live = Boolean(tick)
  const eventTime = live ? parseTimestamp(tick.time) : null

  return (
    <section className="rp-details" aria-label={`${asset.symbol} details`}>
      <div className="rp-details-head">
        <div className="min-w-0">
          <h3>{asset.symbol}</h3>
          <p>{asset.name} · {asset.type}</p>
        </div>
        <DataTag status={freshness} />
      </div>

      <div className="rp-price num">
        {live ? <LivePrice tick={tick} /> : asset.price}
        {live
          ? <Change value={tick.change_pct_24h} suffix={tick.change_window === '1d' ? ' 1d' : ' 24h'} />
          : <Change value={asset.daily_change_pct} suffix=" 1d" />}
      </div>

      <dl className="rp-fields">
        {live ? (
          <>
            <Field label="Source">{tick.provider === 'yahoo' ? 'Yahoo Finance quote' : 'Exchange feed'}</Field>
            <Field label="Received">{formatAge(now - tick.seenAt)}</Field>
            <Field label={tick.provider === 'yahoo' ? 'Price time' : 'Exchange time'}>
              {eventTime ? exchangeTime.format(eventTime) : '—'}
            </Field>
            {tick.high_24h != null && (
              <>
                <Field label="24h high">{formatPrice(tick.high_24h, asset.symbol)}</Field>
                <Field label="24h low">{formatPrice(tick.low_24h, asset.symbol)}</Field>
                <Field label="24h volume">{formatCompact(tick.volume_24h)}</Field>
              </>
            )}
            {tick.previous_close != null && (
              <Field label="Previous close">{formatPrice(tick.previous_close, asset.symbol)}</Field>
            )}
          </>
        ) : (
          <Field label="Source">{asset.stored ? 'Stored daily closes' : '—'}</Field>
        )}
        {asset.stored && (
          <>
            <Field label="Stored to">{formatAsOfDate(asset.latest_timestamp, { withYear: true })}</Field>
            <Field label="Stored close">{asset.price}</Field>
            <Field label="Total return">{formatPercent(asset.total_return_pct)}</Field>
            <Field label="Volatility (yr)">{formatPercent(asset.annualized_volatility_pct).replace('+', '')}</Field>
            <Field label="Max drawdown">{formatPercent(asset.max_drawdown_pct)}</Field>
          </>
        )}
      </dl>

      <button className="rp-open" onClick={() => onOpenChart(asset.symbol)}>
        <LineChart size={13} /> Explore history
      </button>
    </section>
  )
}

/**
 * Right-hand panel on every dashboard page: a compact watchlist and the details of
 * the selected instrument. Live symbols show the feed price; others show the stored close.
 */
function RightPanel({ assets, ticks, liveStatus, loading, error, selectedSymbol, onSelect, onOpenChart }) {
  const now = useNow(5000)
  const selected = assets.find((asset) => asset.symbol === selectedSymbol) ?? assets[0]

  const freshnessOf = (asset) => (ticks[asset.symbol]
    ? tickStatus(ticks[asset.symbol], liveStatus, now)
    : storedStatus(asset))

  return (
    <aside className="right-panel" aria-label="Watchlist and instrument details">
      <div className="rp-heading">
        <h2>Watchlist</h2>
        <span>{loading ? 'Loading…' : `${assets.length} instruments`}</span>
      </div>

      {error && <p className="rp-message rp-error">Stored assets could not be loaded: {error}</p>}
      {!loading && !error && assets.length === 0 && (
        <p className="rp-message">No instruments yet. Load stored history or wait for the live feed.</p>
      )}

      {assets.length > 0 && (
        <ul className="rp-list">
          {assets.map((asset) => {
            const tick = ticks[asset.symbol]
            const active = selected?.symbol === asset.symbol
            return (
              <li key={asset.symbol}>
                <button
                  className={`rp-row ${active ? 'rp-row-active' : ''}`}
                  onClick={() => onSelect(asset.symbol)}
                  aria-pressed={active}
                >
                  <span className="rp-symbol">
                    <i style={{ background: asset.color }} aria-hidden="true" />
                    {asset.symbol}
                  </span>
                  <span className="rp-row-price num">
                    {tick ? <LivePrice tick={tick} /> : asset.price}
                  </span>
                  {tick ? <Change value={tick.change_pct_24h} /> : <Change value={asset.daily_change_pct} />}
                  <DataTag status={freshnessOf(asset)} />
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {selected && (
        <Details
          asset={selected}
          tick={ticks[selected.symbol]}
          freshness={freshnessOf(selected)}
          now={now}
          onOpenChart={onOpenChart}
        />
      )}
    </aside>
  )
}

export default memo(RightPanel)
