import { useEffect, useState } from 'react'
import { getCftc } from '../api/finpulse'
import SeriesChart from '../components/SeriesChart'
import { formatCompact } from '../lib/format'
import { percentileReading } from '../lib/positioning'

const signedCompact = (value) => (value == null ? '—' : `${value > 0 ? '+' : ''}${formatCompact(value)}`)
const tone = (value) => (value == null ? '' : value >= 0 ? 'up' : 'down')

/** Where speculators stand in 12 futures markets, weekly, from the CFTC's Commitments of Traders. */
export default function PositioningPage() {
  const [state, setState] = useState({ data: null, error: '' })
  const [selected, setSelected] = useState('gold')

  useEffect(() => {
    let cancelled = false
    getCftc()
      .then((data) => { if (!cancelled) setState({ data, error: '' }) })
      .catch((error) => { if (!cancelled) setState({ data: null, error: error.message || 'Unavailable' }) })
    return () => {
      cancelled = true
    }
  }, [])

  const { data, error } = state
  if (error) return <section className="panel empty-panel ix-error">CFTC positioning could not be loaded: {error}</section>
  if (!data) return <section className="panel empty-panel">Loading the latest Commitments of Traders…</section>

  const market = data.markets.find((m) => m.id === selected) ?? data.markets[0]

  return (
    <div className="ix">
      <p className="macro-notice">{data.notes[0]} Latest report: positions as of <b>{data.as_of}</b>.</p>
      {data.stale && <p className="macro-notice ix-warn">The CFTC is not answering ({data.stale}); showing the last report fetched.</p>}

      <section className="panel" aria-label="Positioning by market">
        <div className="table-scroll">
          <table className="rel-table pos-table">
            <thead>
              <tr>
                <th>Market</th><th>Who</th><th className="num">Net contracts</th><th className="num">% of open interest</th>
                <th className="num">1-week change</th><th>Where in 3 years</th><th className="num">Asset managers net</th>
              </tr>
            </thead>
            {data.groups.map((group) => {
              const rows = data.markets.filter((m) => m.group === group)
              if (rows.length === 0) return null
              return (
                <tbody key={group}>
                  <tr className="pos-group"><th colSpan="7">{group}</th></tr>
                  {rows.map((m) => (
                    <tr key={m.id} className={m.id === market.id ? 'pos-active' : ''} onClick={() => setSelected(m.id)}>
                      <td><button className="pos-name" onClick={() => setSelected(m.id)}>{m.name}</button></td>
                      <td>{m.traders}</td>
                      <td className={`num ${tone(m.latest.net)}`}>{signedCompact(m.latest.net)}</td>
                      <td className={`num ${tone(m.latest.net_pct_open_interest)}`}>
                        {m.latest.net_pct_open_interest == null ? '—' : `${m.latest.net_pct_open_interest > 0 ? '+' : ''}${m.latest.net_pct_open_interest}%`}
                      </td>
                      <td className={`num ${tone(m.latest.change_1w)}`}>{signedCompact(m.latest.change_1w)}</td>
                      <td title={percentileReading(m.percentile_3y)}>
                        <span className="pos-bar" aria-hidden="true"><i style={{ left: `${m.percentile_3y ?? 50}%` }} /></span>
                        <span className="pos-pct num">{m.percentile_3y == null ? '—' : m.percentile_3y}</span>
                      </td>
                      <td className="num">{m.latest.asset_managers_net == null ? '—' : signedCompact(m.latest.asset_managers_net)}</td>
                    </tr>
                  ))}
                </tbody>
              )
            })}
          </table>
        </div>
      </section>

      <section className="panel" aria-label={`${market.name} net position history`}>
        <div className="panel-heading">
          <div>
            <h2>{market.name}: {market.traders.toLowerCase()} net position, weekly</h2>
            <p>
              {percentileReading(market.percentile_3y)} Range over {market.range_3y.weeks} weeks: {signedCompact(market.range_3y.min)} to{' '}
              {signedCompact(market.range_3y.max)} contracts{market.units ? ` ${market.units.toLowerCase()}` : ''}.
            </p>
          </div>
        </div>
        <div className="ix-chart-wrap"><SeriesChart points={market.history} precision={0} /></div>
      </section>

      <section className="panel risk-method">
        <h2>How to read this</h2>
        <ul>{data.notes.slice(1).map((note) => <li key={note}>{note}</li>)}</ul>
        <p><a href={data.source_url} target="_blank" rel="noopener noreferrer" className="link-inline">CFTC Commitments of Traders</a></p>
      </section>
    </div>
  )
}
