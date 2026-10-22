import { memo } from 'react'
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  BriefcaseBusiness,
  ChevronDown,
  CircleHelp,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  X,
} from 'lucide-react'
import { LIVE_STATUS_LABEL } from '../lib/liveStatus'

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

function Sidebar({ activeNav, onNavigate, open, onClose, liveStatus }) {
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
                  onClick={() => onNavigate(label)}
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
            <button onClick={() => onNavigate('AI Research')} className="upgrade-link">
              Explore tools <ArrowUpRight size={14} />
            </button>
          </div>
          <button className="nav-link"><Settings size={18} /><span>Settings</span></button>
          <button className="nav-link"><CircleHelp size={18} /><span>Help &amp; support</span></button>
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
