import CandleChart from '../components/CandleChart'
import PriceChart from '../components/PriceChart'
import Watchlist from '../components/Watchlist'

/** Live candlesticks, stored price history, and every tracked asset. */
export default function MarketsPage({
  liveSymbols,
  ticks,
  liveStatus,
  chartSymbol,
  onChartSymbol,
  marketAssets,
  selectedSymbol,
  onSelectSymbol,
  range,
  onRangeChange,
  watchlist,
}) {
  return (
    <>
      <CandleChart
        symbols={liveSymbols}
        symbol={chartSymbol}
        onSymbolChange={onChartSymbol}
        tick={ticks[chartSymbol]}
        liveStatus={liveStatus}
      />

      <div className="page-block">
        <PriceChart
          assets={marketAssets}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelectSymbol}
          range={range}
          onRangeChange={onRangeChange}
        />
      </div>

      <Watchlist
        assets={watchlist.assets}
        totalCount={watchlist.totalCount}
        loading={watchlist.loading}
        filter={watchlist.filter}
        onFilterChange={watchlist.onFilterChange}
        liveTicks={ticks}
        liveStatus={liveStatus}
        onSelect={watchlist.onSelect}
      />
    </>
  )
}
