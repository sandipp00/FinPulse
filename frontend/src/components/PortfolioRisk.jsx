import { useEffect, useMemo, useState } from 'react'
import { getPaperPortfolio } from '../api/finpulse'
import { useAuth } from '../hooks/useAuth'
import { valuePortfolio } from '../lib/portfolio'
import { ROUTES } from '../lib/routes'
import { portfolioVolatility } from '../lib/risk'
import { getAssetDetails } from '../lib/format'
import AppLink from './AppLink'

const CONCENTRATED = 0.5 // one holding above half of the equity

function Bars({ rows }) {
  return (
    <div className="weight-bars">
      {rows.map((row) => (
        <div key={row.label} className="weight-row">
          <span className="weight-label"><i style={{ background: row.color }} />{row.label}</span>
          <span className="weight-track"><b style={{ width: `${Math.min(row.weight * 100, 100)}%`, background: row.color }} /></span>
          <span className="weight-value">{(row.weight * 100).toFixed(1)}%</span>
        </div>
      ))}
    </div>
  )
}

function Account({ ticks, risk }) {
  const [portfolio, setPortfolio] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    getPaperPortfolio()
      .then((result) => {
        if (!cancelled) setPortfolio(result)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const view = useMemo(() => valuePortfolio(portfolio, ticks), [portfolio, ticks])

  const analysis = useMemo(() => {
    if (!view) return null
    const equity = view.totals.equity
    const holdings = view.positions.map((p) => ({ symbol: p.symbol, weight: equity ? p.market_value / equity : 0 }))

    const volatility = Object.fromEntries(risk.assets.map((a) => [a.symbol, a.annualized_volatility_pct]))
    const portfolioVol = portfolioVolatility(holdings, volatility, risk.correlation)
    const unweighted = holdings.every((h) => volatility[h.symbol] != null)
      ? holdings.reduce((sum, h) => sum + h.weight * volatility[h.symbol], 0)
      : null

    return {
      equity,
      cashWeight: equity ? view.totals.cash / equity : 1,
      holdings,
      largest: holdings.reduce((best, h) => (h.weight > (best?.weight ?? 0) ? h : best), null),
      portfolioVol,
      benefit: portfolioVol != null && unweighted != null ? unweighted - portfolioVol : null,
    }
  }, [view, risk])

  if (error) return <p className="signal-error">{error}</p>
  if (!analysis) return <p className="signal-loading">Loading your paper portfolio...</p>

  if (analysis.holdings.length === 0) {
    return (
      <p className="risk-empty">
        Your paper account holds only cash, so there is no market risk to measure yet. Place a trade on the{' '}
        <AppLink href={ROUTES.portfolio} className="link-inline">Portfolio page</AppLink> and it will show up here.
      </p>
    )
  }

  const rows = [
    ...analysis.holdings.map((h) => ({ label: h.symbol, weight: h.weight, color: getAssetDetails(h.symbol).color })),
    { label: 'Cash', weight: analysis.cashWeight, color: '#5A5A5A' },
  ]
  const concentrated = analysis.largest && analysis.largest.weight > CONCENTRATED

  return (
    <div className="portfolio-risk">
      <Bars rows={rows} />
      <ul className="risk-findings">
        <li>
          <b>Largest position:</b> {analysis.largest.symbol} at {(analysis.largest.weight * 100).toFixed(1)}% of your equity.
          {concentrated && <span className="risk-flag"> That is concentrated: one asset moving against you has an outsized effect.</span>}
        </li>
        <li>
          <b>Cash:</b> {(analysis.cashWeight * 100).toFixed(1)}% of your equity is not exposed to the market.
        </li>
        <li>
          {analysis.portfolioVol == null ? (
            <><b>Estimated volatility:</b> not available for every asset you hold yet.</>
          ) : (
            <>
              <b>Estimated volatility of the whole portfolio:</b> {analysis.portfolioVol.toFixed(1)}% a year, from each holding&apos;s
              history and how the holdings have moved together
              {analysis.benefit != null && analysis.benefit > 0.05 && (
                <>. Holding them together lowered it by {analysis.benefit.toFixed(1)} points compared with adding up each one on its own</>
              )}.
            </>
          )}
        </li>
      </ul>
      <p className="risk-note">An estimate from past behaviour, with cash counted as having no volatility. It is not a forecast.</p>
    </div>
  )
}

/** Concentration and estimated volatility of the signed-in user's paper portfolio. */
export default function PortfolioRisk({ ticks, risk }) {
  const { user, loading, verificationRequired } = useAuth()

  if (loading) return <p className="signal-loading">Checking your session...</p>
  if (!user) {
    return (
      <p className="risk-empty">
        <AppLink href={ROUTES.signin} className="link-inline">Sign in</AppLink> to see how concentrated your paper
        portfolio is and how volatile it is likely to be.
      </p>
    )
  }
  if (verificationRequired && !user.email_verified) {
    return <p className="risk-empty">Confirm your email address to use paper trading, then your portfolio risk appears here.</p>
  }
  // Keyed by user so switching accounts never shows the previous person's holdings.
  return <Account key={user.id} ticks={ticks} risk={risk} />
}
