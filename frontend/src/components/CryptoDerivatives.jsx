import { useEffect, useState } from 'react'
import { Activity, Layers, Percent, Scale } from 'lucide-react'
import { getCryptoDerivatives } from '../api/finpulse'
import MetricCard from './MetricCard'
import SeriesChart from './SeriesChart'
import { formatCompact, formatPercent } from '../lib/format'
import { curveReading, dvolReading, fundingReading, nearestFuture, putCallReading } from '../lib/derivatives'

const COINS = [['BTC', 'Bitcoin'], ['ETH', 'Ethereum']]
const REFRESH_MS = 60_000

const signed = (value, digits = 2) => (value == null ? '—' : formatPercent(value, digits))
const price = (value) => (value == null ? '—' : value.toLocaleString('en-US', { maximumFractionDigits: 2 }))

/** Bitcoin and Ethereum derivatives from Deribit: implied volatility, funding, futures curve, options. */
export default function CryptoDerivatives() {
  const [currency, setCurrency] = useState('BTC')
  const [state, setState] = useState({ currency: null, data: null, error: '' })

  useEffect(() => {
    let cancelled = false
    const load = () => getCryptoDerivatives(currency)
      .then((data) => { if (!cancelled) setState({ currency, data, error: '' }) })
      .catch((error) => { if (!cancelled) setState((s) => ({ ...s, currency, error: error.message || 'Unavailable' })) })
    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [currency])

  const data = state.currency === currency ? state.data : null
  const error = state.currency === currency ? state.error : ''
  const quarter = nearestFuture(data?.futures)

  return (
    <section className="panel deriv-panel" aria-label="Crypto derivatives">
      <div className="panel-heading">
        <div>
          <h2>Derivatives</h2>
          <p>What options and futures traders are pricing in. Deribit public market data, refreshed every minute.</p>
        </div>
      </div>
      <div className="at-tabs deriv-tabs" role="tablist" aria-label="Coin">
        {COINS.map(([key, name]) => (
          <button key={key} role="tab" aria-selected={currency === key} className={currency === key ? 'at-tab-active' : ''} onClick={() => setCurrency(key)}>
            {name}
          </button>
        ))}
      </div>

      {!data && !error && <p className="signal-loading">Loading {currency} derivatives from Deribit…</p>}
      {error && !data && <p className="signal-error">Deribit data is unavailable: {error}</p>}
      {data && (
        <>
          {error && <p className="signal-error">Refresh failed ({error}); showing the previous figures.</p>}
          {data.meta.status === 'cached' && <p className="signal-error">{data.meta.notes[0]}</p>}
          <div className="metrics-grid deriv-cards">
            <MetricCard
              label="Implied volatility (DVOL)"
              value={data.dvol.value.toFixed(1)}
              change={data.dvol.change_1d == null ? null : `${data.dvol.change_1d > 0 ? '+' : ''}${data.dvol.change_1d.toFixed(1)} vs yesterday`}
              positive={data.dvol.change_1d >= 0}
              icon={Activity}
              note={`The yearly swing options price in for the next 30 days. ${dvolReading(data.dvol)}`}
            />
            <MetricCard
              label="Funding, last 8 hours"
              value={`${signed(data.perpetual.funding_annualized_pct, 1)}`}
              change="a year"
              positive={data.perpetual.funding_annualized_pct >= 0}
              icon={Percent}
              note={fundingReading(data.perpetual.funding_annualized_pct)}
            />
            <MetricCard
              label="Futures premium, ~3 months"
              value={quarter ? signed(quarter.annualized_pct, 1) : '—'}
              change={quarter ? 'a year' : null}
              positive={quarter ? quarter.annualized_pct >= 0 : true}
              icon={Layers}
              note={curveReading(quarter)}
            />
            <MetricCard
              label="Put/call open interest"
              value={data.options.put_call_ratio == null ? '—' : data.options.put_call_ratio.toFixed(2)}
              icon={Scale}
              note={putCallReading(data.options.put_call_ratio)}
            />
          </div>

          <div className="deriv-grid">
            <div>
              <h3>DVOL, past year</h3>
              <div className="ix-chart-wrap deriv-chart"><SeriesChart points={data.dvol.history} precision={1} /></div>
            </div>
            <div>
              <h3>Funding, daily average (annualized)</h3>
              <div className="ix-chart-wrap deriv-chart"><SeriesChart points={data.perpetual.history} percent precision={1} /></div>
            </div>
            <div>
              <h3>Futures curve</h3>
              <div className="table-scroll">
                <table className="rel-table">
                  <thead><tr><th>Expiry</th><th className="num">Days</th><th className="num">Price</th><th className="num">vs spot</th><th className="num">A year</th></tr></thead>
                  <tbody>
                    <tr>
                      <td>Spot index</td><td className="num">—</td><td className="num">{price(data.perpetual.index_price)}</td><td className="num">—</td><td className="num">—</td>
                    </tr>
                    {data.futures.map((f) => (
                      <tr key={f.instrument}>
                        <td>{f.expiry}</td>
                        <td className="num">{f.days.toFixed(0)}</td>
                        <td className="num">{price(f.mark_price)}</td>
                        <td className={`num ${f.basis_pct >= 0 ? 'up' : 'down'}`}>{signed(f.basis_pct, 2)}</td>
                        <td className={`num ${f.annualized_pct == null ? '' : f.annualized_pct >= 0 ? 'up' : 'down'}`}>{signed(f.annualized_pct, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="deriv-note">A year: the premium spread over the time to expiry. Left blank under two days out, where it is mostly noise.</p>
            </div>
            <div>
              <h3>Implied volatility by expiry</h3>
              <div className="table-scroll">
                <table className="rel-table">
                  <thead><tr><th>Expiry</th><th className="num">Days</th><th className="num">At-the-money strike</th><th className="num">Implied vol</th></tr></thead>
                  <tbody>
                    {data.options.term_structure.map((t) => (
                      <tr key={t.expiry}>
                        <td>{t.expiry}</td>
                        <td className="num">{t.days.toFixed(0)}</td>
                        <td className="num">{price(t.atm_strike)}</td>
                        <td className="num">{t.atm_iv.toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="deriv-note">
                Open interest: {formatCompact(data.options.call_open_interest)} {currency} in calls,
                {' '}{formatCompact(data.options.put_open_interest)} {currency} in puts.
                Perpetual open interest ${formatCompact(data.perpetual.open_interest_usd)}.
              </p>
            </div>
          </div>
          <p className="coverage-foot">
            Source: Deribit public market data, as of {new Date(data.meta.source_timestamp ?? data.meta.retrieved_at).toLocaleTimeString()}.
            Deribit is one exchange, so its prices can differ a little from others. Market data, not advice.
          </p>
        </>
      )}
    </section>
  )
}
