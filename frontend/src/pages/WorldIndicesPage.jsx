import { useEffect, useMemo, useState } from 'react'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { getWorldIndices } from '../api/finpulse'
import DataTag from '../components/DataTag'
import LivePrice from '../components/LivePrice'
import { navigate } from '../hooks/useRoute'
import { useNow } from '../hooks/useNow'
import { assetHref } from '../lib/asset'
import { tickStatus } from '../lib/dataStatus'
import { formatPercent } from '../lib/format'

const localClocks = new Map()

/** The exchange's local time, e.g. "15:42". */
function localTime(timezone, now) {
  if (!localClocks.has(timezone)) {
    localClocks.set(timezone, new Intl.DateTimeFormat('en-GB', { timeZone: timezone, hour: '2-digit', minute: '2-digit' }))
  }
  return localClocks.get(timezone).format(now)
}

function IndexRow({ index, tick, status, now }) {
  const change = tick?.change_pct_24h
  const up = change != null && change >= 0
  return (
    <tr className="wi-row" onClick={() => navigate(assetHref(index.symbol))} title={`Open the ${index.name} page`}>
      <td>
        <span className="wi-name">{index.name}</span>
        <span className="wi-sub">{index.country} · {index.symbol}</span>
      </td>
      <td className="num wi-last">{tick ? <LivePrice tick={tick} /> : '—'}</td>
      <td className={`num wi-change ${change == null ? '' : up ? 'up' : 'down'}`}>
        {change != null && (
          <>
            {up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
            {formatPercent(change)}
          </>
        )}
      </td>
      <td><DataTag status={status} /></td>
      <td className="num wi-time">{localTime(index.timezone, now)}</td>
    </tr>
  )
}

/**
 * World indices: the 15 benchmarks by region, each live from the Yahoo poller while
 * its market is open, tagged CLOSED (last session value) or DELAYED otherwise.
 */
export default function WorldIndicesPage({ ticks = {}, marketStatus = {} }) {
  const [state, setState] = useState({ data: null, error: '' })
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

  const statuses = useMemo(() => Object.fromEntries(
    (state.data?.indices ?? []).map((index) => [index.symbol, tickStatus(ticks[index.symbol], marketStatus, now)]),
  ), [state.data, ticks, marketStatus, now])

  if (state.error) return <section className="panel empty-panel ix-error">World indices could not be loaded: {state.error}</section>
  if (!state.data) return <section className="panel empty-panel">Loading world indices…</section>

  const counts = Object.values(statuses).reduce((acc, status) => ({ ...acc, [status]: (acc[status] ?? 0) + 1 }), {})

  return (
    <div className="ix">
      <p className="macro-notice">
        Live index values from Yahoo Finance, refreshed every 15 seconds (personal use). <b>LIVE</b>: the market is
        open; <b>CLOSED</b>: the last value of the session; <b>DELAYED</b>: Yahoo&apos;s newest value is a few minutes
        old (Hong Kong and Shanghai run about 15 minutes behind). Change is since the previous close. Click an index
        for its chart and news.
        {' '}<span className="wi-counts">Now: {counts.live ?? 0} live · {counts.delayed ?? 0} delayed · {counts.closed ?? 0} closed</span>
      </p>
      <div className="wi-grid">
        {state.data.regions.map((region) => (
          <section key={region} className="panel wi-panel" aria-label={region}>
            <h2 className="at-section-title">{region}</h2>
            <table className="wi-table">
              <thead>
                <tr><th>Index</th><th>Last</th><th>Change</th><th>Status</th><th>Local</th></tr>
              </thead>
              <tbody>
                {state.data.indices.filter((index) => index.region === region).map((index) => (
                  <IndexRow key={index.symbol} index={index} tick={ticks[index.symbol]} status={statuses[index.symbol]} now={now} />
                ))}
              </tbody>
            </table>
          </section>
        ))}
      </div>
    </div>
  )
}
