import { Activity, Link2, ShieldAlert, TrendingDown } from 'lucide-react'
import CorrelationHeatmap from '../components/CorrelationHeatmap'
import MetricCard from '../components/MetricCard'
import PortfolioRisk from '../components/PortfolioRisk'
import RiskTable from '../components/RiskTable'
import { useRisk } from '../hooks/useRisk'
import { averageCorrelation, mostDiversifyingPair } from '../lib/risk'

const short = (symbol) => symbol.replace('/USDT', '').replace('^', '')

/** Volatility, drawdown, value at risk and correlations for every tracked asset. */
export default function RiskPage({ ticks }) {
  const { data, loading, error } = useRisk()

  if (loading) return <p className="signal-loading">Calculating risk figures from daily prices...</p>
  if (error) return <p className="signal-error">Unable to load risk figures: {error}</p>
  if (!data || data.assets.length === 0) {
    return <p className="holdings-empty">No price history is available yet, so there is nothing to measure.</p>
  }

  const { assets, correlation } = data
  const most = assets.reduce((a, b) => (b.annualized_volatility_pct > a.annualized_volatility_pct ? b : a))
  const lowest = assets.reduce((a, b) => (b.current_drawdown_pct < a.current_drawdown_pct ? b : a))
  const average = averageCorrelation(correlation)
  const diversifier = mostDiversifyingPair(correlation)

  return (
    <>
      <section className="metrics-grid">
        <MetricCard
          label="Most volatile"
          value={short(most.symbol)}
          change={`${most.annualized_volatility_pct.toFixed(1)}% / yr`}
          positive={false}
          icon={Activity}
          note="Biggest price swings, annualized"
        />
        <MetricCard
          label="Furthest below its high"
          value={short(lowest.symbol)}
          change={`${lowest.current_drawdown_pct.toFixed(1)}%`}
          positive={false}
          icon={TrendingDown}
          note="Latest close vs its highest close"
        />
        <MetricCard
          label="Average correlation"
          value={average == null ? '—' : average.toFixed(2)}
          change="All pairs"
          positive={average != null && average < 0.5}
          icon={Link2}
          note="Closer to 1 means assets move together"
        />
        <MetricCard
          label="Best diversifier"
          value={diversifier ? `${short(diversifier.a)} + ${short(diversifier.b)}` : '—'}
          change={diversifier ? `${diversifier.value.toFixed(2)} corr` : 'n/a'}
          positive
          icon={ShieldAlert}
          note="The pair that moves least together"
        />
      </section>

      {data.notes.length > 0 && (
        <div className="risk-notes" role="status">
          {data.notes.map((note) => <p key={note}>{note}</p>)}
        </div>
      )}

      <section className="panel risk-panel">
        <div className="panel-heading">
          <div>
            <h2>Risk by asset</h2>
            <p>Click a column to sort. Hover a heading for what it means.</p>
          </div>
        </div>
        <RiskTable assets={assets} />
      </section>

      <section className="panel risk-panel">
        <div className="panel-heading">
          <div>
            <h2>How assets move together</h2>
            <p>Correlation of daily returns. Assets that move together protect you less when one falls.</p>
          </div>
        </div>
        <CorrelationHeatmap correlation={correlation} />
      </section>

      <section className="panel risk-panel">
        <div className="panel-heading">
          <div>
            <h2>Your portfolio</h2>
            <p>Concentration and estimated volatility of your paper-trading holdings</p>
          </div>
        </div>
        <PortfolioRisk ticks={ticks} risk={data} />
      </section>

      <section className="panel risk-panel risk-method">
        <h2>How these are measured</h2>
        <ul>
          <li><b>Volatility:</b> {data.methodology.volatility}</li>
          <li><b>1-in-20 day:</b> {data.methodology.var_95} {data.methodology.expected_shortfall}</li>
          <li><b>Drawdown:</b> {data.methodology.drawdown}</li>
          <li><b>Correlation:</b> {data.methodology.correlation}</li>
        </ul>
        <p>{data.methodology.caveat} Crypto uses about three years of daily Binance candles; stocks and indices use the stored history.</p>
      </section>
    </>
  )
}
