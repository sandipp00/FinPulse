import { useEffect, useMemo, useState } from 'react'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { getMarketHours } from '../api/finpulse'
import DataTag from '../components/DataTag'
import LivePrice from '../components/LivePrice'
import { useNow } from '../hooks/useNow'
import { navigate } from '../hooks/useRoute'
import { assetHref } from '../lib/asset'
import { tickStatus } from '../lib/dataStatus'
import { formatPercent } from '../lib/format'
import { formatCountdown, fxMarketOpen, sessionBar, sessionStatus, sortExchanges } from '../lib/marketHours'
import { futuresMarketOpen } from '../lib/metals'

// The timeline shows 4 hours back and 20 ahead, so every session due today is on it.
const BEFORE = 4 * 3600
const AFTER = 20 * 3600
const REFRESH_MS = 5 * 60 * 1000

const clocks = new Map()
function clock(timezone) {
  const key = timezone ?? 'local'
  if (!clocks.has(key)) {
    clocks.set(key, new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', ...(timezone ? { timeZone: timezone } : {}) }))
  }
  return clocks.get(key)
}
const dayTime = new Intl.DateTimeFormat('en-GB', { weekday: 'short', hour: '2-digit', minute: '2-digit' })

function Change({ value }) {
  if (value == null) return null
  const up = value >= 0
  return (
    <span className={`num mh-change ${up ? 'up' : 'down'}`}>
      {up ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}{formatPercent(value)}
    </span>
  )
}

function StatusPill({ status }) {
  if (status.state === 'unknown') return <span className="mh-pill mh-pill-unknown">Hours loading</span>
  const open = status.state === 'open'
  const when = status.seconds == null ? '' : ` · ${open ? 'closes' : 'opens'} in ${formatCountdown(status.seconds)}`
  return (
    <span className={`mh-pill ${open ? 'mh-pill-open' : 'mh-pill-closed'}`} title={status.estimated ? 'Estimated: same hours on the next trading day; holidays are not known' : undefined}>
      {open ? 'Open' : 'Closed'}{when}{status.estimated && !open ? '*' : ''}
    </span>
  )
}

function ExchangeRow({ exchange, now, windowStart, windowEnd, tick, tag }) {
  const status = sessionStatus(exchange.session, now)
  const bar = sessionBar(exchange.session, windowStart, windowEnd)
  const nowPct = ((now - windowStart) / (windowEnd - windowStart)) * 100
  return (
    <div className="mh-row" onClick={() => navigate(assetHref(exchange.benchmark))} role="link" tabIndex={0}
      onKeyDown={(event) => event.key === 'Enter' && navigate(assetHref(exchange.benchmark))}>
      <div className="mh-name">
        <strong>{exchange.city}</strong>
        <small>{exchange.name} · {clock(exchange.timezone).format(now * 1000)} local</small>
      </div>
      <div className="mh-status"><StatusPill status={status} /></div>
      <div className="mh-track" aria-hidden="true">
        {bar && (
          <span
            className={`mh-bar ${status.state === 'open' ? 'mh-bar-open' : ''} ${exchange.session?.estimated ? 'mh-bar-estimated' : ''}`}
            style={{ left: `${bar.left}%`, width: `${bar.width}%` }}
            title={`${dayTime.format(exchange.session.start * 1000)} – ${clock().format(exchange.session.end * 1000)} your time`}
          />
        )}
        <span className="mh-now" style={{ left: `${nowPct}%` }} />
      </div>
      <div className="mh-quote">
        <span className="mh-bench">{exchange.benchmark_name}</span>
        <span className="mh-value">
          {tick ? <LivePrice tick={tick} /> : '—'}
          <Change value={tick?.change_pct_24h} />
          {tick && <DataTag status={tag} />}
        </span>
      </div>
    </div>
  )
}

function OtherMarket({ name, detail, open, tick, tag }) {
  return (
    <div className="panel mh-other">
      <div className="mh-other-top">
        <strong>{name}</strong>
        <span className={`mh-pill ${open ? 'mh-pill-open' : 'mh-pill-closed'}`}>{open ? 'Open' : 'Closed'}</span>
      </div>
      <small>{detail}</small>
      <span className="mh-value">
        {tick ? <LivePrice tick={tick} /> : '—'}
        <Change value={tick?.change_pct_24h} />
        {tick && <DataTag status={tag} />}
      </span>
    </div>
  )
}

/**
 * Market hours: which exchanges are open now, when each opens or closes, a 24-hour
 * timeline of today's sessions in your time, and each market's live benchmark.
 */
export default function MarketHoursPage({ ticks = {}, marketStatus = {} }) {
  const [state, setState] = useState({ data: null, error: '' })
  const nowMs = useNow(15_000)
  const now = Math.floor(nowMs / 1000)

  useEffect(() => {
    let cancelled = false
    let timer = null
    const load = () => {
      getMarketHours()
        .then((data) => !cancelled && setState({ data, error: '' }))
        .catch((err) => !cancelled && setState((current) => ({ ...current, error: err.message || 'Unable to load market hours.' })))
        .finally(() => {
          if (!cancelled) timer = setTimeout(load, REFRESH_MS)
        })
    }
    load()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [])

  const exchanges = useMemo(() => sortExchanges(state.data?.exchanges ?? [], now), [state.data, now])
  const windowStart = now - BEFORE
  const windowEnd = now + AFTER
  const ticksAt = useMemo(() => {
    const first = Math.ceil(windowStart / 10800) * 10800
    return Array.from({ length: 8 }, (_, i) => first + i * 10800).filter((t) => t < windowEnd)
  }, [windowStart, windowEnd])

  if (!state.data && state.error) return <section className="panel empty-panel ix-error">Market hours could not be loaded: {state.error}</section>
  if (!state.data) return <section className="panel empty-panel">Loading market hours…</section>

  const open = exchanges.filter((e) => sessionStatus(e.session, now).state === 'open')
  const nextOpen = exchanges.find((e) => sessionStatus(e.session, now).state === 'closed' && sessionStatus(e.session, now).seconds != null)
  const tag = (symbol) => tickStatus(ticks[symbol], marketStatus, nowMs)

  return (
    <div className="ix">
      <section className="panel mh-summary">
        <div><span>Your time</span><strong className="num">{clock().format(nowMs)}</strong></div>
        <div><span>Exchanges open</span><strong className="num">{open.length} of {exchanges.length}</strong></div>
        <div>
          <span>Next to open</span>
          <strong>{nextOpen ? `${nextOpen.city} in ${formatCountdown(sessionStatus(nextOpen.session, now).seconds)}` : '—'}</strong>
        </div>
        <div>
          <span>Next to close</span>
          <strong>{open[0] ? `${open[0].city} in ${formatCountdown(sessionStatus(open[0].session, now).seconds)}` : '—'}</strong>
        </div>
      </section>

      <section className="mh-others" aria-label="Markets that trade around the clock">
        <OtherMarket name="Crypto" detail="Trades 24/7 · Bitcoin" open tick={ticks['BTC/USDT']} tag={tag('BTC/USDT')} />
        <OtherMarket name="FX" detail="Sun 17:00 – Fri 17:00 New York · EUR/USD" open={fxMarketOpen(new Date(nowMs))} tick={ticks['EUR/USD']} tag={tag('EUR/USD')} />
        <OtherMarket name="Gold, silver & oil futures" detail="Sun 18:00 – Fri 17:00 New York, daily break 17:00 · Gold" open={futuresMarketOpen(new Date(nowMs))} tick={ticks['XAU/USDT']} tag={tag('XAU/USDT')} />
      </section>

      <section className="panel mh-panel" aria-label="Stock exchange hours">
        <div className="mh-head">
          <div className="mh-name"><strong>Stock exchanges</strong><small>Open first, then the next to open</small></div>
          <div className="mh-status" />
          <div className="mh-axis" aria-hidden="true">
            {ticksAt.map((t) => (
              <span key={t} style={{ left: `${((t - windowStart) / (windowEnd - windowStart)) * 100}%` }}>{clock().format(t * 1000)}</span>
            ))}
          </div>
          <div className="mh-quote"><span className="mh-bench">Benchmark</span></div>
        </div>
        {exchanges.map((exchange) => (
          <ExchangeRow
            key={exchange.id}
            exchange={exchange}
            now={now}
            windowStart={windowStart}
            windowEnd={windowEnd}
            tick={ticks[exchange.benchmark]}
            tag={tag(exchange.benchmark)}
          />
        ))}
        <p className="ix-footnote">
          Bars show each regular session in your time; the line is now. Hours from Yahoo Finance. * After a session ends
          the next one is estimated (same local hours on the next trading day). {state.data.notes[1]} Click an exchange
          for its benchmark&apos;s chart and news.
        </p>
      </section>
    </div>
  )
}
