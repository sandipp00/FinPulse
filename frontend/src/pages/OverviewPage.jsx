import { Activity, ArrowUpRight, ShieldCheck, TrendingUp, Wallet } from 'lucide-react'
import AppLink from '../components/AppLink'
import AssetMix from '../components/AssetMix'
import DataStatus from '../components/DataStatus'
import LiveMarket from '../components/LiveMarket'
import MetricCard from '../components/MetricCard'
import QuickLinks from '../components/QuickLinks'
import { formatPercent } from '../lib/format'
import { ROUTES } from '../lib/routes'

/** The summary: headline numbers, live crypto, what is tracked, and where to go next. */
export default function OverviewPage({
  marketAssets,
  displayAssets,
  assetLoading,
  apiError,
  ticks,
  history,
  liveSymbols,
  liveStatus,
  chartSymbol,
  onOpenChart,
}) {
  const bestReturn = marketAssets.length
    ? Math.max(...marketAssets.map((asset) => Number(asset.total_return_pct ?? -Infinity)).filter(Number.isFinite))
    : null

  const averageVolatility = marketAssets.length
    ? marketAssets.reduce((sum, asset) => sum + (Number(asset.annualized_volatility_pct) || 0), 0) / marketAssets.length
    : null

  const worstDrawdown = marketAssets.length
    ? Math.min(...marketAssets.map((asset) => Number(asset.max_drawdown_pct ?? Infinity)).filter(Number.isFinite))
    : null

  return (
    <>
      <section className="metrics-grid">
        <MetricCard
          label="Tracked assets"
          value={assetLoading ? 'Loading...' : String(displayAssets.length)}
          change="SQLite + live"
          positive
          icon={Wallet}
          note="Stored history plus live crypto streams"
        />
        <MetricCard
          label="Best historical return"
          value={bestReturn == null ? '—' : formatPercent(bestReturn)}
          change="Full history"
          positive={bestReturn != null && bestReturn >= 0}
          icon={TrendingUp}
          note="Highest return across stored assets"
        />
        <MetricCard
          label="Average annualized volatility"
          value={averageVolatility == null ? '—' : `${averageVolatility.toFixed(2)}%`}
          change="Risk metric"
          positive={false}
          icon={Activity}
          note="Average across stored assets"
        />
        <MetricCard
          label="Worst historical drawdown"
          value={worstDrawdown == null ? '—' : `${worstDrawdown.toFixed(2)}%`}
          change="Risk metric"
          positive={false}
          icon={ShieldCheck}
          note="Largest peak-to-trough decline"
        />
      </section>

      <LiveMarket
        ticks={ticks}
        history={history}
        symbols={liveSymbols}
        status={liveStatus}
        selectedSymbol={chartSymbol}
        onSelect={onOpenChart}
      />

      <section className="charts-grid">
        <QuickLinks />
        <AssetMix assets={displayAssets} />
      </section>

      <section className="bottom-grid">
        <div className="panel insight-panel">
          <div className="insight-icon"><ShieldCheck size={19} /></div>
          <div className="min-w-0 flex-1">
            <h2>Know the risk before the return</h2>
            <p>
              See how volatile each asset is, how far it has fallen from its highs, and which assets move
              together, using the same data you see here.
            </p>
          </div>
          <AppLink href={ROUTES.risk} className="insight-button">
            Open risk monitor <ArrowUpRight size={15} />
          </AppLink>
        </div>
        <DataStatus apiError={apiError} loading={assetLoading} liveStatus={liveStatus} />
      </section>
    </>
  )
}
