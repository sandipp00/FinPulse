import { useCallback, useEffect, useMemo, useState } from 'react'
import AccountLinkBanner from './components/AccountLinkBanner'
import LiveTicker from './components/LiveTicker'
import RightPanel from './components/RightPanel'
import Sidebar from './components/Sidebar'
import StatusBar from './components/StatusBar'
import ToastStack from './components/ToastStack'
import Topbar from './components/Topbar'
import { useAssets } from './hooks/useAssets'
import { useBackendStatus } from './hooks/useBackendStatus'
import { LivePricesContext } from './context/live-prices-context'
import { useAuth } from './hooks/useAuth'
import { useLivePrices } from './hooks/useLivePrices'
import { useNotificationFeeds, useNotifications } from './hooks/useNotifications'
import { navigate } from './hooks/useRoute'
import { apiState, latestStoredTimestamp } from './lib/dataStatus'
import { formatPercent, formatPrice, getAssetDetails } from './lib/format'
import { isLiveMetal } from './lib/metals'
import { PAGES } from './lib/pages'
import { ROUTES } from './lib/routes'
import AnalyticsPage from './pages/AnalyticsPage'
import AssetClassPage from './pages/AssetClassPage'
import AssistantPage from './pages/AssistantPage'
import CalendarPage from './pages/CalendarPage'
import CommoditiesPage from './pages/CommoditiesPage'
import ExplorerPage from './pages/ExplorerPage'
import FxPage from './pages/FxPage'
import MacroPage from './pages/MacroPage'
import NewsPage from './pages/NewsPage'
import HelpPage from './pages/HelpPage'
import MarketsPage from './pages/MarketsPage'
import OverviewPage from './pages/OverviewPage'
import PortfolioPage from './pages/PortfolioPage'
import ResearchPage from './pages/ResearchPage'
import RiskPage from './pages/RiskPage'
import SettingsPage from './pages/SettingsPage'

const TYPE_LABEL = { crypto: 'Crypto', index: 'Index', stock: 'Stock', commodity: 'Commodity' }

// Pages that show the stored-asset list, and so should say when it is loading or failed.
const USES_ASSET_DATA = new Set(['home', 'equities', 'crypto', 'markets', 'analytics'])

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
  // The right panel's selection is its own, so picking a live-only coin there does
  // not point the stored-history chart at an asset it has no data for.
  const [panelSymbol, setPanelSymbol] = useState('BTC/USDT')
  // Fixed for the visit: day-level ages do not need a ticking clock.
  const [pageLoadedAt] = useState(() => Date.now())

  const { assets: marketAssets, loading: assetLoading, error: apiError } = useAssets()
  const { ticks, history, status: liveStatus, metalsStatus } = useLivePrices()
  const { user, logout } = useAuth()
  const { unread } = useNotifications()
  const backend = useBackendStatus()

  // Price alerts are checked against every tick, and daily ratings are polled for changes.
  useNotificationFeeds(ticks)

  // Show the unread count in the browser tab, so a notification is noticed from another tab.
  useEffect(() => {
    document.title = unread > 0 ? `(${unread}) FinPulse` : 'FinPulse'
    return () => {
      document.title = 'FinPulse'
    }
  }, [unread])

  // Symbols the server streams live. The stored list only knows what is in
  // SQLite, so the live set is whatever has ticked plus the stored crypto.
  // Keyed on the symbol names rather than `ticks` itself: ticks change every
  // fraction of a second, but the list of symbols almost never does, and a
  // stable list lets the panels that depend on it skip re-rendering.
  // Live gold and silver tick on the same socket but are kept apart: the crypto-only
  // pages (signals, paper trading, live market) use `liveSymbols`.
  const tickSymbolKey = Object.keys(ticks).filter((symbol) => !isLiveMetal(ticks[symbol])).join(',')
  const metalSymbolKey = Object.keys(ticks).filter((symbol) => isLiveMetal(ticks[symbol])).join(',')
  const metalSymbols = useMemo(() => (metalSymbolKey ? metalSymbolKey.split(',') : []), [metalSymbolKey])
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
    const liveMetals = metalSymbols.map((symbol) => ({
      symbol,
      asset_type: 'commodity',
      stored: false,
      type: 'Commodity',
    }))

    return [...stored, ...liveOnly, ...liveMetals].map((asset) => {
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
  }, [marketAssets, liveSymbols, metalSymbols])

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
    setPanelSymbol(symbol)
    if (route !== 'markets') navigate(ROUTES.markets)
    else window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [route])

  // The right panel's "Explore history" opens the explorer on that instrument.
  const openExplorer = useCallback((symbol) => {
    setPanelSymbol(symbol)
    navigate(`${ROUTES.explorer}?symbol=${encodeURIComponent(symbol)}`)
  }, [])

  const livePrices = useMemo(() => ({ ticks, symbols: liveSymbols }), [ticks, liveSymbols])

  // Stocks, indices and metals have no live feed; the ticker shows their stored close, dated.
  const storedTickerAssets = useMemo(
    () => marketAssets.filter((asset) => asset.asset_type !== 'crypto'),
    [marketAssets],
  )
  const storedAsOf = useMemo(() => latestStoredTimestamp(marketAssets), [marketAssets])

  return (
    <LivePricesContext.Provider value={livePrices}>
      <div className="app-shell">
        <Sidebar
          route={route}
          onNavigate={closeSidebar}
          open={sidebarOpen}
          onClose={closeSidebar}
        />

        <main className="main-panel">
          <Topbar
            pageTitle={page.title}
            search={search}
            onSearch={handleSearch}
            onOpenMenu={openSidebar}
            user={user}
            onLogout={logout}
            apiStatus={apiState(backend)}
            liveStatus={liveStatus}
          />

          <LiveTicker
            ticks={ticks}
            symbols={liveSymbols}
            status={liveStatus}
            metalSymbols={metalSymbols}
            metalsStatus={metalsStatus}
            storedAssets={storedTickerAssets}
          />

          <div className="workspace">
            <div className="dashboard-content">
              <AccountLinkBanner />

              <section className="page-intro">
                <h1>{page.title}</h1>
                <p>{page.blurb}</p>
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
              {(route === 'equities' || route === 'crypto') && (
                <AssetClassPage
                  assetClass={route}
                  assets={displayAssets}
                  ticks={ticks}
                  liveStatus={liveStatus}
                  loading={assetLoading}
                  error={apiError}
                  onSelect={openChart}
                  now={pageLoadedAt}
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
              {route === 'fx' && <FxPage />}
              {route === 'commodities' && (
                <CommoditiesPage
                  marketAssets={marketAssets}
                  assetLoading={assetLoading}
                  assetError={apiError}
                  ticks={ticks}
                  metalSymbols={metalSymbols}
                  metalsStatus={metalsStatus}
                />
              )}
              {route === 'macro' && <MacroPage />}
              {route === 'news' && <NewsPage />}
              {route === 'calendar' && <CalendarPage />}
              {route === 'explorer' && <ExplorerPage />}
              {route === 'assistant' && <AssistantPage />}
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
            </div>

            <RightPanel
              assets={displayAssets}
              ticks={ticks}
              liveStatus={liveStatus}
              loading={assetLoading}
              error={apiError}
              selectedSymbol={panelSymbol}
              onSelect={setPanelSymbol}
              onOpenChart={openExplorer}
            />
          </div>
        </main>
        <StatusBar
          backend={backend}
          liveStatus={liveStatus}
          ticks={ticks}
          storedAsOf={storedAsOf}
          assetsLoading={assetLoading}
          assetsError={apiError}
        />
        <ToastStack />
      </div>
    </LivePricesContext.Provider>
  )
}

export default Dashboard
