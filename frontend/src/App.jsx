import { useMemo, useState } from 'react'
import {
  Activity,
  ArrowUpRight,
  ChevronDown,
  CreditCard,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import AssetMix from './components/AssetMix'
import CandleChart from './components/CandleChart'
import DataStatus from './components/DataStatus'
import LiveMarket from './components/LiveMarket'
import LiveTicker from './components/LiveTicker'
import MetricCard from './components/MetricCard'
import PriceChart from './components/PriceChart'
import Sidebar from './components/Sidebar'
import SignalsPanel from './components/SignalsPanel'
import Topbar from './components/Topbar'
import Watchlist from './components/Watchlist'
import { useAssets } from './hooks/useAssets'
import { useLivePrices } from './hooks/useLivePrices'
import { LIVE_STATUS_LABEL } from './lib/liveStatus'
import { formatPercent, formatPrice, getAssetDetails } from './lib/format'

const TYPE_LABEL = { crypto: 'Crypto', index: 'Index', stock: 'Stock' }

function App() {
  const [activeNav, setActiveNav] = useState('Overview')
  const [range, setRange] = useState('1W')
  const [filter, setFilter] = useState('All assets')
  const [search, setSearch] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT')
  const [chartSymbol, setChartSymbol] = useState('BTC/USDT')

  const { assets: marketAssets, loading: assetLoading, error: apiError } = useAssets()
  const { ticks, history, status: liveStatus } = useLivePrices()

  // Symbols the server streams live. The stored list only knows what is in
  // SQLite, so the live set is whatever has ticked plus the stored crypto.
  const liveSymbols = useMemo(() => {
    const symbols = new Set(Object.keys(ticks))
    marketAssets.forEach((asset) => {
      if (asset.asset_type === 'crypto') symbols.add(asset.symbol)
    })
    return [...symbols]
  }, [ticks, marketAssets])

  // Stored assets, plus any live-only coins (e.g. SOL) with no stored history.
  const displayAssets = useMemo(() => {
    const stored = marketAssets.map((asset) => ({
      ...asset,
      stored: true,
      type: TYPE_LABEL[asset.asset_type] ?? 'Stock',
    }))
    const storedSymbols = new Set(stored.map((asset) => asset.symbol))

    const liveOnly = liveSymbols
      .filter((symbol) => !storedSymbols.has(symbol))
      .map((symbol) => ({
        symbol,
        asset_type: 'crypto',
        stored: false,
        type: 'Crypto',
      }))

    return [...stored, ...liveOnly].map((asset) => {
      const details = getAssetDetails(asset.symbol)
      return {
        ...asset,
        name: details.name,
        color: details.color,
        price: formatPrice(asset.latest_price, asset.symbol),
        change: formatPercent(asset.daily_change_pct),
        positive: Number(asset.daily_change_pct) >= 0,
      }
    })
  }, [marketAssets, liveSymbols])

  const filteredAssets = useMemo(() => displayAssets.filter((asset) => {
    const matchesType = filter === 'All assets' || asset.type === filter
    const matchesSearch = `${asset.symbol} ${asset.name}`
      .toLowerCase()
      .includes(search.toLowerCase())
    return matchesType && matchesSearch
  }), [displayAssets, filter, search])

  const bestReturn = marketAssets.length
    ? Math.max(...marketAssets.map((asset) => Number(asset.total_return_pct ?? -Infinity))
      .filter(Number.isFinite))
    : null

  const averageVolatility = marketAssets.length
    ? marketAssets.reduce(
      (sum, asset) => sum + (Number(asset.annualized_volatility_pct) || 0),
      0,
    ) / marketAssets.length
    : null

  const worstDrawdown = marketAssets.length
    ? Math.min(...marketAssets.map((asset) => Number(asset.max_drawdown_pct ?? Infinity))
      .filter(Number.isFinite))
    : null

  const pageTitle = activeNav === 'Overview' ? 'Market overview' : activeNav

  const navigate = (label) => {
    setActiveNav(label)
    setSidebarOpen(false)
  }

  return (
    <div className="app-shell">
      <Sidebar
        activeNav={activeNav}
        onNavigate={navigate}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        liveStatus={liveStatus}
      />

      <main className="main-panel">
        <Topbar
          pageTitle={pageTitle}
          search={search}
          onSearch={setSearch}
          onOpenMenu={() => setSidebarOpen(true)}
        />

        <LiveTicker ticks={ticks} symbols={liveSymbols} status={liveStatus} />

        <div className="dashboard-content">
          <section className="page-intro">
            <div>
              <div className="eyebrow"><span className="status-dot" /> YOUR FINANCIAL COMMAND CENTER</div>
              <h1>{pageTitle}<span>.</span></h1>
              <p>Track markets, understand risk, and make data-informed decisions.</p>
            </div>
            <div className="date-button">
              <span className={`status-dot ${liveStatus === 'live' ? '' : 'status-muted'}`} />
              {LIVE_STATUS_LABEL[liveStatus]}
              <ChevronDown size={15} />
            </div>
          </section>

          {assetLoading && (
            <p className="mb-4 text-sm text-slate-400">Loading market data from your local database...</p>
          )}
          {apiError && (
            <p className="mb-4 rounded-lg border border-red-900 bg-red-950/40 p-3 text-sm text-red-300">
              Unable to load market data: {apiError}
            </p>
          )}

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
            onSelect={setChartSymbol}
          />

          <CandleChart
            symbols={liveSymbols}
            symbol={chartSymbol}
            onSymbolChange={setChartSymbol}
            tick={ticks[chartSymbol]}
            liveStatus={liveStatus}
          />

          <SignalsPanel selectedSymbol={chartSymbol} onSelect={setChartSymbol} />

          <section className="charts-grid">
            <PriceChart
              assets={marketAssets}
              selectedSymbol={selectedSymbol}
              onSelectSymbol={setSelectedSymbol}
              range={range}
              onRangeChange={setRange}
            />
            <AssetMix assets={displayAssets} />
          </section>

          <Watchlist
            assets={filteredAssets}
            totalCount={displayAssets.length}
            loading={assetLoading}
            filter={filter}
            onFilterChange={setFilter}
            liveTicks={ticks}
            onSelect={(symbol) => {
              setSelectedSymbol(symbol)
              setActiveNav('Analytics')
            }}
          />

          <section className="bottom-grid">
            <div className="panel insight-panel">
              <div className="insight-icon"><Sparkles size={19} /></div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2>AI research workspace</h2>
                  <span className="coming-soon">PREVIEW</span>
                </div>
                <p>Explore historical returns, volatility, drawdowns, and price trends from your local financial dataset.</p>
              </div>
              <button className="insight-button" onClick={() => setActiveNav('AI Research')}>
                Explore <ArrowUpRight size={15} />
              </button>
            </div>
            <DataStatus apiError={apiError} loading={assetLoading} liveStatus={liveStatus} />
          </section>

          <footer className="app-footer">
            <span>FinPulse <span className="footer-version">DEVELOPER PREVIEW</span></span>
            <span><CreditCard size={13} /> Research &amp; analytics workspace</span>
            <span>Market data is informational only. Not investment advice.</span>
          </footer>
        </div>
      </main>
    </div>
  )
}

export default App
