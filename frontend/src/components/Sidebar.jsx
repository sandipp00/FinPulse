import { memo } from 'react'
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  BookOpen,
  BriefcaseBusiness,
  ChevronRight,
  CircleHelp,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  TrendingUp,
  X,
} from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { LIVE_STATUS_LABEL } from '../lib/liveStatus'
import { PAGES } from '../lib/pages'
import { ROUTES } from '../lib/routes'
import AppLink from './AppLink'

const NAV_GROUPS = [
  {
    title: 'WORKSPACE',
    items: [
      { route: 'home', icon: LayoutDashboard },
      { route: 'markets', icon: TrendingUp },
      { route: 'portfolio', icon: BriefcaseBusiness },
      { route: 'analytics', icon: BarChart3 },
    ],
  },
  {
    title: 'TOOLS',
    items: [
      { route: 'research', icon: BookOpen },
      { route: 'risk', icon: ShieldCheck },
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
      <Icon size={18} />
      <span>{PAGES[route].nav}</span>
    </AppLink>
  )
}

function Sidebar({ route, onNavigate, open, onClose, liveStatus }) {
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

        <nav className="mt-8 flex-1" aria-label="Main">
          {NAV_GROUPS.map((group) => (
            <div className="mb-7" key={group.title}>
              <p className="nav-heading">{group.title}</p>
              {group.items.map((item) => (
                <NavLink key={item.route} {...item} active={route === item.route} onNavigate={onNavigate} />
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="upgrade-card">
            <div className="flex items-center gap-2 text-emerald-300">
              <BookOpen size={17} />
              <span className="text-sm font-semibold">Read the research brief</span>
            </div>
            <p className="mt-2 text-xs leading-5 text-slate-400">
              A plain-language summary of each asset, written from your own data.
            </p>
            <AppLink href={ROUTES.research} onClick={onNavigate} className="upgrade-link">
              Open research <ArrowUpRight size={14} />
            </AppLink>
          </div>
          <NavLink route="settings" icon={Settings} active={route === 'settings'} onNavigate={onNavigate} />
          <NavLink route="help" icon={CircleHelp} active={route === 'help'} onNavigate={onNavigate} />
          <div className="sidebar-footer">
            <span className={`status-dot ${liveStatus === 'live' ? '' : 'status-muted'}`} />
            {LIVE_STATUS_LABEL[liveStatus]}
          </div>
        </div>
      </aside>
    </>
  )
}

export default memo(Sidebar)
