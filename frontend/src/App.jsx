import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Bitcoin,
  BriefcaseBusiness,
  ChevronDown,
  CircleHelp,
  Command,
  CreditCard,
  LayoutDashboard,
  Menu,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Wallet,
  X,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getAssets, getPrices } from './api/finpulse'

const navGroups = [
  {
    title: 'WORKSPACE',
    items: [
      { label: 'Overview', icon: LayoutDashboard },
      { label: 'Markets', icon: TrendingUp },
      { label: 'Portfolio', icon: BriefcaseBusiness },
      { label: 'Analytics', icon: BarChart3 },
    ],
  },
  {
    title: 'TOOLS',
    items: [
      { label: 'AI Research', icon: Sparkles },
      { label: 'Risk Monitor', icon: ShieldCheck },
    ],
  },
]

const assetDetails = {
  AAPL: { name: 'Apple Inc.', color: '#A5B4FC', currency: 'USD' },
  'BTC/USDT': { name: 'Bitcoin', color: '#F7931A', currency: 'USD' },
  'ETH/USDT': { name: 'Ethereum', color: '#818CF8', currency: 'USD' },
  '^NSEI': { name: 'Nifty 50', color: '#34D399', currency: 'INR' },
}

function formatPrice(value, symbol) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const currency = assetDetails[symbol]?.currency ?? 'USD'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(Number(value))
}

function formatPercent(value, digits = 2) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const number = Number(value)
  return `${number > 0 ? '+' : ''}${number.toFixed(digits)}%`
}

function MetricCard({ label, value, change, positive, icon: Icon, note }) {
  return (
    <div className="metric-card">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-slate-400">{label}</p>
        <span className="icon-tile"><Icon size={18} /></span>
      </div>
      <div className="mt-5 flex flex-wrap items-baseline gap-2">
        <h2 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">{value}</h2>
        {change && (
          <span className={`change-pill ${positive ? 'positive' : 'negative'}`}>
            {positive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
            {change}
          </span>
        )}
      </div>
      <p className="mt-2 text-xs text-slate-500">{note}</p>
    </div>
  )
}

function App() {
  const [activeNav, setActiveNav] = useState('Overview')
  const [range, setRange] = useState('1W')
  const [filter, setFilter] = useState('All assets')
  const [search, setSearch] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const [marketAssets, setMarketAssets] = useState([])
  const [assetLoading, setAssetLoading] = useState(true)
  const [apiError, setApiError] = useState('')
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT')
  const [priceHistory, setPriceHistory] = useState([])
  const [priceLoading, setPriceLoading] = useState(false)

  useEffect(() => {
    let cancelled = false

    getAssets()
      .then((result) => {
        if (cancelled) return
        setMarketAssets(Array.isArray(result.assets) ? result.assets : [])
        setApiError('')
      })
      .catch((error) => {
        if (!cancelled) setApiError(error.message || 'Unable to load market assets.')
      })
      .finally(() => {
        if (!cancelled) setAssetLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setPriceLoading(true)

    getPrices(selectedSymbol, 2000)
      .then((result) => {
        if (cancelled) return
        setPriceHistory(Array.isArray(result.prices) ? result.prices : [])
      })
      .catch((error) => {
        if (!cancelled) {
          setPriceHistory([])
          setApiError(error.message || 'Unable to load historical prices.')
        }
      })
      .finally(() => {
        if (!cancelled) setPriceLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [selectedSymbol])

  const displayAssets = useMemo(
    () => marketAssets.map((asset) => {
      const details = assetDetails[asset.symbol] ?? {
        name: asset.symbol,
        color: '#94A3B8',
        currency: 'USD',
      }

      const type = asset.asset_type === 'crypto'
        ? 'Crypto'
        : asset.asset_type === 'index'
          ? 'Index'
          : 'Stock'

      return {
        ...asset,
        name: details.name,
        color: details.color,
        type,
        price: formatPrice(asset.latest_price, asset.symbol),
        change: formatPercent(asset.daily_change_pct),
        positive: Number(asset.daily_change_pct) >= 0,
      }
    }),
    [marketAssets],
  )

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

  const historicalChartData = useMemo(() => {
    const sorted = [...priceHistory].sort(
      (a, b) => new Date(a.timestamp) - new Date(b.timestamp),
    )
    const periods = { '1D': 2, '1W': 7, '1M': 30, '3M': 90, '1Y': 365 }
    const selectedPeriod = periods[range]
    const visible = selectedPeriod
      ? sorted.slice(-Math.min(selectedPeriod, sorted.length))
      : sorted

    return visible.map((item) => ({
      date: new Date(item.timestamp).toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
      }),
      timestamp: item.timestamp,
      price: Number(item.close),
      volume: Number(item.volume),
    })).filter((item) => Number.isFinite(item.price))
  }, [priceHistory, range])

  const selectedAsset = marketAssets.find((asset) => asset.symbol === selectedSymbol)
  const latestChartPrice = historicalChartData.at(-1)?.price
  const firstChartPrice = historicalChartData[0]?.price
  const chartReturn = firstChartPrice
    ? ((latestChartPrice / firstChartPrice) - 1) * 100
    : null

  const assetTypeAllocation = useMemo(() => {
    const colors = { Crypto: '#34D399', Stock: '#818CF8', Index: '#FBBF24' }
    const counts = displayAssets.reduce((result, asset) => {
      result[asset.type] = (result[asset.type] || 0) + 1
      return result
    }, {})
    return Object.entries(counts).map(([name, value]) => ({
      name: name === 'Index' ? 'Indices' : `${name}${value > 1 ? 's' : ''}`,
      value,
      color: colors[name] ?? '#94A3B8',
    }))
  }, [displayAssets])

  const totalTracked = assetTypeAllocation.reduce((sum, item) => sum + item.value, 0)

  return (
    <div className="app-shell">
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          onClick={() => setSidebarOpen(false)}
          aria-label="Close navigation"
        />
      )}

      <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><Activity size={22} strokeWidth={2.5} /></div>
          <div>
            <div className="brand-name">FinPulse<span>.</span></div>
            <div className="brand-caption">FINANCIAL INTELLIGENCE</div>
          </div>
          <button className="mobile-close" onClick={() => setSidebarOpen(false)} aria-label="Close menu">
            <X size={20} />
          </button>
        </div>

        <button className="workspace-switch">
          <div className="workspace-avatar">S</div>
          <div className="min-w-0 flex-1 text-left">
            <div className="truncate text-sm font-medium text-white">Personal workspace</div>
            <div className="mt-1 text-xs text-slate-500">Local project</div>
          </div>
          <ChevronDown size={16} className="text-slate-500" />
        </button>

        <nav className="mt-8 flex-1">
          {navGroups.map((group) => (
            <div className="mb-7" key={group.title}>
              <p className="nav-heading">{group.title}</p>
              {group.items.map(({ label, icon: Icon }) => (
                <button
                  key={label}
                  onClick={() => {
                    setActiveNav(label)
                    setSidebarOpen(false)
                  }}
                  className={`nav-link ${activeNav === label ? 'nav-link-active' : ''}`}
                >
                  <Icon size={18} />
                  <span>{label}</span>
                  {label === 'AI Research' && <span className="nav-new">AI</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="upgrade-card">
            <div className="flex items-center gap-2 text-emerald-300">
              <Sparkles size={17} />
              <span className="text-sm font-semibold">Research smarter</span>
            </div>
            <p className="mt-2 text-xs leading-5 text-slate-400">
              Explore your market data with AI-powered insights.
            </p>
            <button onClick={() => setActiveNav('AI Research')} className="upgrade-link">
              Explore tools <ArrowUpRight size={14} />
            </button>
          </div>
          <button className="nav-link"><Settings size={18} /><span>Settings</span></button>
          <button className="nav-link"><CircleHelp size={18} /><span>Help &amp; support</span></button>
          <div className="sidebar-footer"><span className="status-dot" /> API connection configured</div>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="flex min-w-0 items-center gap-3">
            <button className="mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
              <Menu size={21} />
            </button>
            <div className="breadcrumb">
              <span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{pageTitle}</strong>
            </div>
          </div>
          <div className="topbar-actions">
            <label className="search-box">
              <Search size={16} />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search assets..."
                aria-label="Search assets"
              />
              <kbd>⌘ K</kbd>
            </label>
            <button className="icon-button" aria-label="Notifications">
              <Bell size={18} /><span className="notification-dot" />
            </button>
            <div className="top-avatar">SP</div>
          </div>
        </header>

        <div className="dashboard-content">
          <section className="page-intro">
            <div>
              <div className="eyebrow"><span className="status-dot" /> YOUR FINANCIAL COMMAND CENTER</div>
              <h1>{pageTitle}<span>.</span></h1>
              <p>Track markets, understand risk, and make data-informed decisions.</p>
            </div>
            <div className="date-button">
              <span className="status-dot" />
              Historical SQLite data
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
              value={assetLoading ? 'Loading...' : String(marketAssets.length)}
              change="SQLite"
              positive
              icon={Wallet}
              note="Assets in your local database"
            />
            <MetricCard
              label="Best historical return"
              value={bestReturn == null ? '—' : formatPercent(bestReturn)}
              change="Full history"
              positive={bestReturn != null && bestReturn >= 0}
              icon={TrendingUp}
              note="Highest return across tracked assets"
            />
            <MetricCard
              label="Average annualized volatility"
              value={averageVolatility == null ? '—' : `${averageVolatility.toFixed(2)}%`}
              change="Risk metric"
              positive={false}
              icon={Activity}
              note="Average across tracked assets"
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

          <section className="charts-grid">
            <div className="panel performance-panel">
              <div className="panel-heading">
                <div>
                  <h2>Historical price analytics</h2>
                  <p>Closing prices loaded from your SQLite database</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={selectedSymbol}
                    onChange={(event) => setSelectedSymbol(event.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200"
                    aria-label="Select asset for historical chart"
                  >
                    {marketAssets.map((asset) => (
                      <option key={asset.symbol} value={asset.symbol}>{asset.symbol}</option>
                    ))}
                  </select>
                  <div className="range-control">
                    {['1D', '1W', '1M', '3M', '1Y'].map((item) => (
                      <button
                        key={item}
                        onClick={() => setRange(item)}
                        className={range === item ? 'range-active' : ''}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="chart-summary">
                <strong>{latestChartPrice == null ? '—' : formatPrice(latestChartPrice, selectedSymbol)}</strong>
                {chartReturn != null && (
                  <span className={`change-pill ${chartReturn >= 0 ? 'positive' : 'negative'}`}>
                    {chartReturn >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                    {formatPercent(chartReturn)}
                  </span>
                )}
                <span className="text-xs text-slate-500">
                  {selectedAsset ? `${selectedAsset.observations} stored observations` : 'Historical data'}
                </span>
              </div>

              <div className="chart-legend">
                <span><i className="legend-dot emerald" /> {selectedSymbol} closing price</span>
              </div>

              <div className="performance-chart">
                {priceLoading ? (
                  <div className="flex h-full items-center justify-center text-sm text-slate-400">
                    Loading historical prices...
                  </div>
                ) : historicalChartData.length === 0 ? (
                  <div className="flex h-full items-center justify-center text-sm text-slate-400">
                    No historical prices are available for this selection.
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={historicalChartData} margin={{ top: 12, right: 5, left: -8, bottom: 0 }}>
                      <defs>
                        <linearGradient id="historicalGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#34D399" stopOpacity={0.24} />
                          <stop offset="100%" stopColor="#34D399" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#1E293B" strokeDasharray="3 5" vertical={false} />
                      <XAxis
                        dataKey="date"
                        minTickGap={24}
                        tick={{ fill: '#64748B', fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        width={70}
                        tick={{ fill: '#64748B', fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(value) => Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}
                      />
                      <Tooltip
                        contentStyle={{ background: '#101827', border: '1px solid #263347', borderRadius: 12, color: '#E2E8F0' }}
                        labelStyle={{ color: '#94A3B8' }}
                        formatter={(value) => [formatPrice(value, selectedSymbol), 'Closing price']}
                      />
                      <Area
                        type="monotone"
                        dataKey="price"
                        name="Closing price"
                        stroke="#34D399"
                        strokeWidth={2.5}
                        fill="url(#historicalGradient)"
                        dot={false}
                        activeDot={{ r: 4, fill: '#34D399', stroke: '#0B1220', strokeWidth: 2 }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </div>
              <div className="chart-footnote">
                <span><i className="status-dot" /> Historical records from local database</span>
                <span>Range: {range}</span>
              </div>
            </div>

            <div className="panel allocation-panel">
              <div className="panel-heading">
                <div>
                  <h2>Tracked asset mix</h2>
                  <p>Count of assets by market type, not portfolio allocation</p>
                </div>
                <button className="subtle-icon" aria-label="Asset mix information"><Command size={17} /></button>
              </div>
              <div className="allocation-chart">
                {totalTracked > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={assetTypeAllocation}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={66}
                        outerRadius={91}
                        paddingAngle={5}
                        stroke="none"
                      >
                        {assetTypeAllocation.map((entry) => (
                          <Cell key={entry.name} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{ background: '#101827', border: '1px solid #263347', borderRadius: 12, color: '#E2E8F0' }}
                        formatter={(value, name) => [`${value} asset${value === 1 ? '' : 's'}`, name]}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-slate-400">No assets loaded</div>
                )}
                <div className="allocation-center">
                  <span>Tracked</span>
                  <strong>{totalTracked}</strong>
                </div>
              </div>
              <div className="allocation-legend">
                {assetTypeAllocation.map((item) => (
                  <div key={item.name} className="allocation-row">
                    <span className="allocation-label"><i style={{ background: item.color }} />{item.name}</span>
                    <strong>{item.value} ({totalTracked ? Math.round(item.value / totalTracked * 100) : 0}%)</strong>
                  </div>
                ))}
              </div>
              <div className="allocation-note">
                <ShieldCheck size={15} />
                <span>This visual summarizes database coverage; it does not represent invested capital.</span>
              </div>
            </div>
          </section>

          <section className="panel assets-panel">
            <div className="panel-heading assets-heading">
              <div>
                <h2>Market watchlist</h2>
                <p>Latest stored prices and daily changes from SQLite</p>
              </div>
              <div className="asset-filters">
                {['All assets', 'Stock', 'Crypto', 'Index'].map((item) => (
                  <button
                    key={item}
                    onClick={() => setFilter(item)}
                    className={filter === item ? 'filter-active' : ''}
                  >
                    {item === 'Stock' ? 'Stocks' : item === 'Index' ? 'Indices' : item}
                  </button>
                ))}
              </div>
            </div>

            <div className="table-scroll">
              <table className="market-table">
                <thead>
                  <tr>
                    <th>ASSET</th>
                    <th>TYPE</th>
                    <th>LATEST STORED PRICE</th>
                    <th>DAILY CHANGE</th>
                    <th>HISTORICAL RETURN</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {filteredAssets.map((asset) => (
                    <tr key={asset.symbol}>
                      <td>
                        <div className="asset-cell">
                          <span
                            className="asset-icon"
                            style={{
                              color: asset.color,
                              borderColor: `${asset.color}44`,
                              background: `${asset.color}12`,
                            }}
                          >
                            {asset.symbol === 'BTC/USDT'
                              ? <Bitcoin size={20} />
                              : asset.symbol === '^NSEI'
                                ? <BarChart3 size={18} />
                                : asset.symbol === 'AAPL' ? 'A' : 'Ξ'}
                          </span>
                          <span><strong>{asset.symbol}</strong><small>{asset.name}</small></span>
                        </div>
                      </td>
                      <td><span className="type-label">{asset.type}</span></td>
                      <td className="price-cell">{asset.price}</td>
                      <td>
                        <span className={`change-pill ${asset.positive ? 'positive' : 'negative'}`}>
                          {asset.positive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                          {asset.change}
                        </span>
                      </td>
                      <td className="price-cell">{formatPercent(asset.total_return_pct)}</td>
                      <td>
                        <button
                          className="row-action"
                          onClick={() => {
                            setSelectedSymbol(asset.symbol)
                            setActiveNav('Analytics')
                          }}
                          aria-label={`View ${asset.symbol} historical prices`}
                        >
                          <ArrowUpRight size={17} />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!assetLoading && filteredAssets.length === 0 && (
                    <tr><td colSpan="6" className="empty-state">No assets match your search.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="table-footer">
              <span>{assetLoading ? 'Loading assets...' : `Showing ${filteredAssets.length} of ${marketAssets.length} tracked assets`}</span>
              <span>Prices reflect the latest stored records, not guaranteed live quotes.</span>
            </div>
          </section>

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
            <div className="panel data-status">
              <div className="flex items-center gap-2">
                <DatabaseIcon />
                <h2>Data connectivity</h2>
              </div>
              <p>FastAPI connected to local SQLite database</p>
              <div className="connection-row">
                <span className={`status-dot ${apiError ? 'status-muted' : ''}`} />
                <span>{apiError ? 'API request needs attention' : assetLoading ? 'Checking API connection...' : 'Connected · read-only access'}</span>
                <span className="connection-badge">{apiError ? 'CHECK' : 'LOCAL API'}</span>
              </div>
            </div>
          </section>

          <footer className="app-footer">
            <span>FinPulse <span className="footer-version">DEVELOPER PREVIEW</span></span>
            <span><CreditCard size={13} /> Research &amp; analytics workspace</span>
            <span>Historical analysis only. Not investment advice.</span>
          </footer>
        </div>
      </main>
    </div>
  )
}

function DatabaseIcon() {
  return <div className="icon-tile"><BarChart3 size={17} /></div>
}

export default App
