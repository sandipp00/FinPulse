import { Fragment, useEffect, useMemo, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, Search, X } from 'lucide-react'
import { getWorldIndices } from '../api/finpulse'
import DataTag from '../components/DataTag'
import LivePrice from '../components/LivePrice'
import { navigate } from '../hooks/useRoute'
import { useNow } from '../hooks/useNow'
import { assetHref } from '../lib/asset'
import { tickStatus } from '../lib/dataStatus'
import { formatPercent, formatPrice } from '../lib/format'
import { filterIndices, netChange, regionSummary } from '../lib/worldIndices'

const localClocks = new Map()

/** The exchange's local time, e.g. "15:42". */
function localTime(timezone, now) {
  if (!localClocks.has(timezone)) {
    localClocks.set(timezone, new Intl.DateTimeFormat('en-GB', { timeZone: timezone, hour: '2-digit', minute: '2-digit' }))
  }
  return localClocks.get(timezone).format(now)
}

const tone = (value) => (value == null ? '' : value >= 0 ? 'up' : 'down')
const points = (value) => (value == null ? '—' : `${value >= 0 ? '+' : ''}${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)

function IndexRow({ index, tick, status, now }) {
  const change = tick?.change_pct_24h
  const net = netChange(tick)
  return (
    <tr className="wi-row" onClick={() => navigate(assetHref(index.symbol))} title={`Open the ${index.name} page`}>
      <td className="wi-index">
        <span className="wi-name">{index.name}</span>
        <span className="wi-sub">{index.symbol}</span>
      </td>
      <td className="wi-country">{index.country}</td>
      <td className="num wi-last">{tick ? <LivePrice tick={tick} /> : '—'}</td>
      <td className={`num ${tone(net)}`}>{points(net)}</td>
      <td className={`num wi-change ${tone(change)}`}>
        {change != null && (
          <>
            {change >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
            {formatPercent(change)}
          </>
        )}
      </td>
      <td className="num wi-prev">{tick?.previous_close != null ? formatPrice(tick.previous_close, index.symbol) : '—'}</td>
      <td className="wi-status"><DataTag status={status} /></td>
      <td className="num wi-time">{localTime(index.timezone, now)}</td>
    </tr>
  )
}

function RegionHeader({ region, summary, columns }) {
  return (
    <tr className="wi-region">
      <th colSpan={columns}>
        <span className="wi-region-name">{region}</span>
        <span className="wi-region-meta">
          {summary.open} of {summary.count} open
          {' · '}<span className="up">{summary.up} up</span>{' · '}<span className="down">{summary.down} down</span>
          {summary.averageChange != null && (
            <>{' · average '}<b className={tone(summary.averageChange)}>{formatPercent(summary.averageChange)}</b></>
          )}
        </span>
      </th>
    </tr>
  )
}

/**
 * World indices: every index in one table, grouped by region with the same columns
 * throughout, live from the quote poller and tagged LIVE, DELAYED or CLOSED.
 */
export default function WorldIndicesPage({ ticks = {}, marketStatus = {} }) {
  const [state, setState] = useState({ data: null, error: '' })
  const [region, setRegion] = useState('all')
  const [query, setQuery] = useState('')
  const now = useNow(5000)

  useEffect(() => {
    let cancelled = false
    getWorldIndices()
      .then((data) => !cancelled && setState({ data, error: '' }))
      .catch((err) => !cancelled && setState({ data: null, error: err.message || 'Unable to load indices.' }))
    return () => {
      cancelled = true
    }
  }, [])

  const indices = useMemo(() => state.data?.indices ?? [], [state.data])
  const statuses = useMemo(() => Object.fromEntries(
    indices.map((index) => [index.symbol, tickStatus(ticks[index.symbol], marketStatus, now)]),
  ), [indices, ticks, marketStatus, now])
  const shown = useMemo(() => filterIndices(indices, { region, query }), [indices, region, query])

  if (state.error) return <section className="panel empty-panel ix-error">World indices could not be loaded: {state.error}</section>
  if (!state.data) return <section className="panel empty-panel">Loading world indices…</section>

  const regions = state.data.regions
  const total = regionSummary(indices, ticks, statuses)
  const COLUMNS = 8

  return (
    <div className="ix">
      <section className="panel wi-summary" aria-label="Summary">
        <div><span>Indices</span><strong className="num">{total.count}</strong></div>
        <div><span>Open now</span><strong className="num">{total.open}</strong></div>
        <div><span>Live (not delayed)</span><strong className="num">{total.live}</strong></div>
        <div><span>Up · down today</span><strong className="num"><span className="up">{total.up}</span> · <span className="down">{total.down}</span></strong></div>
        <div><span>Average change</span><strong className={`num ${tone(total.averageChange)}`}>{total.averageChange == null ? '—' : formatPercent(total.averageChange)}</strong></div>
      </section>

      <section className="panel wi-panel" aria-label="World indices">
        <div className="wi-toolbar">
          <div className="at-tabs wi-tabs" role="tablist" aria-label="Region">
            {['all', ...regions].map((key) => {
              const count = key === 'all' ? indices.length : indices.filter((index) => index.region === key).length
              return (
                <button key={key} role="tab" aria-selected={region === key} className={region === key ? 'at-tab-active' : ''} onClick={() => setRegion(key)}>
                  {key === 'all' ? 'All' : key}<span className="at-tab-count">{count}</span>
                </button>
              )
            })}
          </div>
          <div className="sb-search wi-search">
            <Search size={14} aria-hidden="true" />
            <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search: DAX, Japan, ^NSEI…" aria-label="Search indices" />
            {query && <button onClick={() => setQuery('')} aria-label="Clear search"><X size={14} /></button>}
          </div>
        </div>

        <div className="table-scroll">
          <table className="wi-table">
            <thead>
              <tr>
                <th>Index</th>
                <th>Country</th>
                <th className="num">Last</th>
                <th className="num">Change</th>
                <th className="num">%</th>
                <th className="num">Prev close</th>
                <th>Status</th>
                <th className="num">Local</th>
              </tr>
            </thead>
            <tbody>
              {regions.map((name) => {
                const rows = shown.filter((index) => index.region === name)
                if (rows.length === 0) return null
                return (
                  <Fragment key={name}>
                    <RegionHeader region={name} summary={regionSummary(rows, ticks, statuses)} columns={COLUMNS} />
                    {rows.map((index) => (
                      <IndexRow key={index.symbol} index={index} tick={ticks[index.symbol]} status={statuses[index.symbol]} now={now} />
                    ))}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
          {shown.length === 0 && <p className="at-empty">No index matches “{query}”.</p>}
        </div>

        <p className="ix-footnote">
          Live index values from Yahoo Finance every 15 seconds (Shanghai, Shenzhen and Hang Seng from Tencent Finance),
          personal use. <b>LIVE</b>: the market is open; <b>DELAYED</b>: the newest value is a few minutes old (Yahoo runs
          several exchanges about 15 minutes behind); <b>CLOSED</b>: the last value of the session. Change is since the
          previous close. Click an index for its chart and news.
        </p>
      </section>
    </div>
  )
}
