import AssetComparison from '../components/AssetComparison'
import SignalsPanel from '../components/SignalsPanel'

/** Buy/sell signals with their backtests, plus a side-by-side look at the stored history. */
export default function AnalyticsPage({ chartSymbol, onSelectSymbol, marketAssets }) {
  return (
    <>
      <SignalsPanel selectedSymbol={chartSymbol} onSelect={onSelectSymbol} />
      <AssetComparison assets={marketAssets} />
    </>
  )
}
