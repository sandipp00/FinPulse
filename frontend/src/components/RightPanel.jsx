import { memo, useState } from 'react'
import { ArrowDown, ArrowDownRight, ArrowUp, ArrowUpRight, LineChart, MonitorDot, Pencil, X } from 'lucide-react'
import { useNow } from '../hooks/useNow'
import { formatAge, formatAsOfDate, parseTimestamp, storedStatus, tickStatus } from '../lib/dataStatus'
import { formatCompact, formatPercent, formatPrice } from '../lib/format'
import { MAX_ITEMS, add, move, remove } from '../lib/watchlist'
import DataTag from './DataTag'
import InstrumentSearch from './InstrumentSearch'
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

const SOURCE_LABEL = { yahoo: 'Yahoo Finance quote', tencent: 'Tencent Finance quote' }

function Details({ asset, tick, freshness, now, onOpenChart, onOpenAsset }) {
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
            <Field label="Source">{SOURCE_LABEL[tick.provider] ?? 'Exchange feed'}</Field>
            <Field label="Received">{formatAge(now - tick.seenAt)}</Field>
            <Field label={SOURCE_LABEL[tick.provider] ? 'Price time' : 'Exchange time'}>
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

      {onOpenAsset && (
        <button className="rp-open" onClick={() => onOpenAsset(asset.symbol)}>
          <MonitorDot size={13} /> Asset terminal: price, chart and news
        </button>
      )}
      <button className="rp-open" onClick={() => onOpenChart(asset.symbol)}>
        <LineChart size={13} /> Explore history
      </button>
    </section>
  )
}

/** Edit the watchlist: add from every instrument, reorder, remove; save, cancel or go back to the default. */
function Editor({ initial, instruments, watchlist, onDone }) {
  const [draft, setDraft] = useState(initial)
  const save = async (symbols) => {
    if (await watchlist.save(symbols)) onDone()
  }
  const full = draft.length >= MAX_ITEMS
  return (
    <div className="rp-editor">
      <InstrumentSearch
        label="Add"
        instruments={instruments}
        value=""
        onChange={(symbol) => setDraft((list) => add(list, symbol))}
        disabledReason={(item) => (draft.includes(item.symbol) ? 'in the list' : full ? `the list holds ${MAX_ITEMS}` : null)}
      />
      <ul className="rp-list rp-edit-list">
        {draft.map((symbol, i) => (
          <li key={symbol} className="rp-edit-row">
            <span className="rp-symbol">{symbol}</span>
            <button onClick={() => setDraft((list) => move(list, i, -1))} disabled={i === 0} aria-label={`Move ${symbol} up`}><ArrowUp size={13} /></button>
            <button onClick={() => setDraft((list) => move(list, i, 1))} disabled={i === draft.length - 1} aria-label={`Move ${symbol} down`}><ArrowDown size={13} /></button>
            <button onClick={() => setDraft((list) => remove(list, symbol))} aria-label={`Remove ${symbol}`}><X size={13} /></button>
          </li>
        ))}
        {draft.length === 0 && <li className="rp-message">Empty. Add instruments above, or go back to the default list.</li>}
      </ul>
      {watchlist.error && <p className="rp-message rp-error">{watchlist.error}</p>}
      <div className="rp-edit-actions">
        <button className="rp-open" onClick={() => save(draft)} disabled={watchlist.saving || draft.length === 0}>
          {watchlist.saving ? 'Saving…' : 'Save'}
        </button>
        <button className="rp-open" onClick={onDone}>Cancel</button>
        <button className="rp-open" onClick={() => save([])} disabled={watchlist.saving}>Default list</button>
      </div>
      <p className="rp-message">{watchlist.signedIn ? 'Saved to your account.' : 'Saved in this browser. Sign in to keep it on your account.'}</p>
    </div>
  )
}

/**
 * Right-hand panel on every dashboard page: a compact watchlist and the details of
 * the selected instrument. Live symbols show the feed price; others show the stored close.
 * With `watchlist`, the list can be edited (see hooks/useWatchlist).
 */
function RightPanel({ assets, ticks, liveStatus, loading, error, selectedSymbol, onSelect, onOpenChart, onOpenAsset, watchlist, instruments = [] }) {
  const now = useNow(5000)
  const [editing, setEditing] = useState(false)
  const selected = assets.find((asset) => asset.symbol === selectedSymbol) ?? assets[0]

  const freshnessOf = (asset) => (ticks[asset.symbol]
    ? tickStatus(ticks[asset.symbol], liveStatus, now)
    : storedStatus(asset))

  return (
    <aside className="right-panel" aria-label="Watchlist and instrument details">
      <div className="rp-heading">
        <h2>Watchlist</h2>
        <span>
          {loading ? 'Loading…' : `${assets.length} instruments${watchlist?.custom ? ', yours' : ''}`}
          {watchlist && !editing && (
            <button className="rp-edit" onClick={() => setEditing(true)} aria-label="Edit the watchlist" title="Edit the watchlist">
              <Pencil size={12} /> Edit
            </button>
          )}
        </span>
      </div>

      {editing && (
        <Editor initial={assets.map((asset) => asset.symbol)} instruments={instruments} watchlist={watchlist} onDone={() => setEditing(false)} />
      )}

      {error && <p className="rp-message rp-error">Stored assets could not be loaded: {error}</p>}
      {!loading && !error && assets.length === 0 && (
        <p className="rp-message">No instruments yet. Load stored history or wait for the live feed.</p>
      )}

      {!editing && assets.length > 0 && (
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
          onOpenAsset={onOpenAsset}
        />
      )}
    </aside>
  )
}

export default memo(RightPanel)
