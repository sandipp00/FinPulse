import { useState } from 'react'
import AnalysisScoreboard from '../components/AnalysisScoreboard'
import AssetAnalysis from '../components/AssetAnalysis'
import AssetComparison from '../components/AssetComparison'
import SignalsPanel from '../components/SignalsPanel'

/**
 * Analysis for every asset: a scoreboard of all of them and a full analysis of the
 * chosen one, then the crypto buy/sell signals with their backtests and the
 * side-by-side look at the stored history.
 */
export default function AnalyticsPage({ chartSymbol, onSelectSymbol, marketAssets }) {
  const [assetId, setAssetId] = useState('btc')

  const pick = (id) => {
    setAssetId(id)
    document.getElementById('asset-analysis')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <>
      <AnalysisScoreboard selected={assetId} onSelect={pick} />
      <div className="page-block">
        <AssetAnalysis assetId={assetId} onSelect={setAssetId} />
      </div>
      <div className="page-block">
        <SignalsPanel selectedSymbol={chartSymbol} onSelect={onSelectSymbol} />
      </div>
      <AssetComparison assets={marketAssets} />
    </>
  )
}
