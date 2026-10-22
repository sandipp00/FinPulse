import { useCallback, useMemo, useState } from 'react'
import { ChevronDown, CreditCard } from 'lucide-react'
import AccountLinkBanner from './components/AccountLinkBanner'
import LiveTicker from './components/LiveTicker'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import { useAssets } from './hooks/useAssets'
import { useAuth } from './hooks/useAuth'
import { useLivePrices } from './hooks/useLivePrices'
import { navigate } from './hooks/useRoute'
import { LIVE_STATUS_LABEL } from './lib/liveStatus'
import { formatPercent, formatPrice, getAssetDetails } from './lib/format'
import { PAGES } from './lib/pages'
import { ROUTES } from './lib/routes'
import AnalyticsPage from './pages/AnalyticsPage'
import HelpPage from './pages/HelpPage'
import MarketsPage from './pages/MarketsPage'
import OverviewPage from './pages/OverviewPage'
import PortfolioPage from './pages/PortfolioPage'
import ResearchPage from './pages/ResearchPage'
import RiskPage from './pages/RiskPage'
import SettingsPage from './pages/SettingsPage'

const TYPE_LABEL = { crypto: 'Crypto', index: 'Index', stock: 'Stock' }

// Pages that show the stored-asset list, and so should say when it is loading or failed.
const USES_ASSET_DATA = new Set(['home', 'markets', 'analytics'])

/**
 * The shared shell (sidebar, top bar, live price ticker) and the data every page
 * draws on. Which page appears in the content area follows the URL.
 */
function Dashboard({ route }) {
  const [range, setRange] = useState('1W')
  const [filter, setFilter] = useState('All assets')
  const [search, setSearch] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT')
  const [chartSymbol, setChartSymbol] = useState('BTC/USDT')

  const { assets: marketAssets, loading: assetLoading, error: apiError } = useAssets()
  const { ticks, history, status: liveStatus } = useLivePrices()
  const { user, logout } = useAuth()

  // Symbols the server streams live. The stored list only knows what is in
  // SQLite, so the live set is whatever has ticked plus the stored crypto.
  // Keyed on the symbol names rather than `ticks` itself: ticks change every
  // fraction of a second, but the list of symbols almost never does, and a
  // stable list lets the panels that depend on it skip re-rendering.
  const tickSymbolKey = Object.keys(ticks).join(',')
  const liveSymbols = useMemo(() => {
    const symbols = new Set(tickSymbolKey ? tickSymbolKey.split(',') : [])
    marketAssets.forEach((asset) => {
      if (asset.asset_type === 'crypto') symbols.add(asset.symbol)
    })
    return [...symbols]
  }, [tickSymbolKey, marketAssets])

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

  const page = PAGES[route]

  const closeSidebar = useCallback(() => setSidebarOpen(false), [])
  const openSidebar = useCallback(() => setSidebarOpen(true), [])

  // The search box filters the watchlist, which lives on the Markets page, so
  // typing into it from anywhere takes you there.
  const handleSearch = useCallback((value) => {
    setSearch(value)
    if (value && route !== 'markets') navigate(ROUTES.markets)
  }, [route])

  // A live card (Overview) or a watchlist row (Markets) opens that asset's chart.
  const openChart = useCallback((symbol) => {
    setChartSymbol(symbol)
    setSelectedSymbol(symbol)
    if (route !== 'markets') navigate(ROUTES.markets)
    else window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [route])

  return (
    <div className="app-shell">
      <Sidebar
        route={route}
        onNavigate={closeSidebar}
        open={sidebarOpen}
        onClose={closeSidebar}
        liveStatus={liveStatus}
      />

      <main className="main-panel">
        <Topbar
          pageTitle={page.title}
          search={search}
          onSearch={handleSearch}
          onOpenMenu={openSidebar}
          user={user}
          onLogout={logout}
        />

        <LiveTicker ticks={ticks} symbols={liveSymbols} status={liveStatus} />

        <div className="dashboard-content">
          <AccountLinkBanner />

          <section className="page-intro">
            <div>
              <div className="eyebrow"><span className="status-dot" /> YOUR FINANCIAL COMMAND CENTER</div>
              <h1>{page.title}<span>.</span></h1>
              <p>{page.blurb}</p>
            </div>
            <div className="date-button">
              <span className={`status-dot ${liveStatus === 'live' ? '' : 'status-muted'}`} />
              {LIVE_STATUS_LABEL[liveStatus]}
              <ChevronDown size={15} />
            </div>
          </section>

          {USES_ASSET_DATA.has(route) && assetLoading && (
            <p className="mb-4 text-sm text-slate-400">Loading market data from your local database...</p>
          )}
          {USES_ASSET_DATA.has(route) && apiError && (
            <p className="mb-4 rounded-lg border border-red-900 bg-red-950/40 p-3 text-sm text-red-300">
              Unable to load market data: {apiError}
            </p>
          )}

          {route === 'home' && (
            <OverviewPage
              marketAssets={marketAssets}
              displayAssets={displayAssets}
              assetLoading={assetLoading}
              apiError={apiError}
              ticks={ticks}
              history={history}
              liveSymbols={liveSymbols}
              liveStatus={liveStatus}
              chartSymbol={chartSymbol}
              onOpenChart={openChart}
            />
          )}
          {route === 'markets' && (
            <MarketsPage
              liveSymbols={liveSymbols}
              ticks={ticks}
              liveStatus={liveStatus}
              chartSymbol={chartSymbol}
              onChartSymbol={setChartSymbol}
              marketAssets={marketAssets}
              selectedSymbol={selectedSymbol}
              onSelectSymbol={setSelectedSymbol}
              range={range}
              onRangeChange={setRange}
              watchlist={{
                assets: filteredAssets,
                totalCount: displayAssets.length,
                loading: assetLoading,
                filter,
                onFilterChange: setFilter,
                onSelect: openChart,
              }}
            />
          )}
          {route === 'portfolio' && (
            <PortfolioPage liveSymbols={liveSymbols} ticks={ticks} liveStatus={liveStatus} />
          )}
          {route === 'analytics' && (
            <AnalyticsPage chartSymbol={chartSymbol} onSelectSymbol={setChartSymbol} marketAssets={marketAssets} />
          )}
          {route === 'research' && (
            <ResearchPage ticks={ticks} liveSymbols={liveSymbols} liveStatus={liveStatus} />
          )}
          {route === 'risk' && <RiskPage ticks={ticks} />}
          {route === 'settings' && <SettingsPage liveStatus={liveStatus} />}
          {route === 'help' && <HelpPage />}

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

export default Dashboard
