import { useMemo } from 'react'
import { ArrowUpRight, ShieldCheck } from 'lucide-react'
import AppLink from '../components/AppLink'
import AssetMix from '../components/AssetMix'
import DataStatus from '../components/DataStatus'
import LiveMarket from '../components/LiveMarket'
import MarketBoard from '../components/MarketBoard'
import OverviewPulse from '../components/OverviewPulse'
import QuickLinks from '../components/QuickLinks'
import { useAssetRegistry } from '../hooks/useAsset'
import { coverage } from '../lib/overview'
import { ROUTES } from '../lib/routes'

/** Where every market stands now, what is moving, and where to go next. */
export default function OverviewPage({
  assetLoading,
  apiError,
  ticks,
  history,
  liveSymbols,
  liveStatus,
  marketStatus,
  chartSymbol,
  onOpenChart,
  onOpenAsset,
}) {
  const registry = useAssetRegistry()
  // Memoized: a new object on every live tick would restart the chart's draw-in animation.
  const counts = useMemo(() => coverage(registry.assets), [registry.assets])

  return (
    <>
      <MarketBoard ticks={ticks} liveStatus={marketStatus} onOpenAsset={onOpenAsset} />

      <OverviewPulse ticks={ticks} onOpenAsset={onOpenAsset} />

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
        <AssetMix counts={counts} />
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
        <DataStatus apiError={apiError} loading={assetLoading} liveStatus={liveStatus} marketStatus={marketStatus} />
      </section>
    </>
  )
}
