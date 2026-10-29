import { memo } from 'react'
import {
  Activity,
  BarChart3,
  Bitcoin,
  BookOpen,
  BriefcaseBusiness,
  Building2,
  CandlestickChart,
  ChevronRight,
  CircleHelp,
  Coins,
  Clock,
  Landmark,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  TrendingUp,
  X,
} from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { PAGES, PLANNED_MODULES } from '../lib/pages'
import { ROUTES } from '../lib/routes'
import AppLink from './AppLink'

const NAV_GROUPS = [
  {
    title: 'MARKETS',
    items: [
      { route: 'home', icon: LayoutDashboard },
      { route: 'equities', icon: Building2 },
      { route: 'crypto', icon: Bitcoin },
      { route: 'fx', icon: Coins },
      { route: 'macro', icon: Landmark },
    ],
    planned: PLANNED_MODULES,
  },
  {
    title: 'RESEARCH',
    items: [
      { route: 'markets', icon: TrendingUp },
      { route: 'explorer', icon: CandlestickChart },
      { route: 'analytics', icon: BarChart3 },
      { route: 'research', icon: BookOpen },
      { route: 'risk', icon: ShieldCheck },
    ],
  },
  {
    title: 'PORTFOLIO',
    items: [
      { route: 'portfolio', icon: BriefcaseBusiness },
    ],
  },
]

function NavLink({ route, icon: Icon, active, onNavigate }) {
  return (
    <AppLink
      href={ROUTES[route]}
      onClick={onNavigate}
      className={`nav-link ${active ? 'nav-link-active' : ''}`}
      aria-current={active ? 'page' : undefined}
    >
      <Icon size={16} />
      <span>{PAGES[route].nav}</span>
    </AppLink>
  )
}

// Not a link: the module has no data yet, so there is no page to open.
function PlannedItem({ nav, note }) {
  return (
    <span className="nav-link nav-link-planned" aria-disabled="true" title={note}>
      <Clock size={16} />
      <span>{nav}</span>
      <span className="nav-planned-tag">PLANNED</span>
      <span className="sr-only">: {note}</span>
    </span>
  )
}

function Sidebar({ route, onNavigate, open, onClose }) {
  const { user } = useAuth()

  return (
    <>
      {open && (
        <button
          className="sidebar-backdrop"
          onClick={onClose}
          aria-label="Close navigation"
        />
      )}

      <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><Activity size={22} strokeWidth={2.5} /></div>
          <div>
            <div className="brand-name">FinPulse<span>.</span></div>
            <div className="brand-caption">FINANCIAL INTELLIGENCE</div>
          </div>
          <button className="mobile-close" onClick={onClose} aria-label="Close menu">
            <X size={20} />
          </button>
        </div>

        <AppLink href={user ? ROUTES.settings : ROUTES.signin} onClick={onNavigate} className="workspace-switch">
          <div className="workspace-avatar">{user ? user.email[0].toUpperCase() : '?'}</div>
          <div className="min-w-0 flex-1 text-left">
            <div className="truncate text-sm font-medium text-white">{user ? user.email : 'Guest'}</div>
            <div className="mt-1 text-xs text-slate-500">{user ? 'Account and settings' : 'Sign in to paper trade'}</div>
          </div>
          <ChevronRight size={16} className="text-slate-500" />
        </AppLink>

        <nav className="sidebar-nav" aria-label="Main">
          {NAV_GROUPS.map((group) => (
            <div className="nav-group" key={group.title}>
              <p className="nav-heading">{group.title}</p>
              {group.items.map((item) => (
                <NavLink key={item.route} {...item} active={route === item.route} onNavigate={onNavigate} />
              ))}
              {group.planned?.map((item) => <PlannedItem key={item.key} {...item} />)}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <NavLink route="settings" icon={Settings} active={route === 'settings'} onNavigate={onNavigate} />
          <NavLink route="help" icon={CircleHelp} active={route === 'help'} onNavigate={onNavigate} />
        </div>
      </aside>
    </>
  )
}

export default memo(Sidebar)
