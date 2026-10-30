import { memo } from 'react'
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  BriefcaseBusiness,
  CandlestickChart,
  MessageSquareText,
  MonitorDot,
  ShieldCheck,
  TrendingUp,
} from 'lucide-react'
import { PAGES } from '../lib/pages'
import { ROUTES } from '../lib/routes'
import AppLink from './AppLink'

const LINKS = [
  { route: 'asset', icon: MonitorDot },
  { route: 'markets', icon: TrendingUp },
  { route: 'explorer', icon: CandlestickChart },
  { route: 'analytics', icon: BarChart3 },
  { route: 'research', icon: BookOpen },
  { route: 'risk', icon: ShieldCheck },
  { route: 'assistant', icon: MessageSquareText },
  { route: 'portfolio', icon: BriefcaseBusiness },
]

/** The overview's "where to next" menu: one row per page, filling the panel's height. */
function QuickLinks() {
  return (
    <div className="panel quick-links">
      <div className="panel-heading">
        <div>
          <h2>Explore</h2>
          <p>Jump into the part of FinPulse you need</p>
        </div>
      </div>
      <nav className="quick-list" aria-label="Explore FinPulse">
        {LINKS.map(({ route, icon: Icon }) => (
          <AppLink key={route} href={ROUTES[route]} className="quick-row">
            <span className="quick-icon"><Icon size={16} /></span>
            <span className="quick-title">{PAGES[route].title}</span>
            <span className="quick-blurb">{PAGES[route].blurb}</span>
            <ArrowRight size={14} className="quick-arrow" />
          </AppLink>
        ))}
      </nav>
    </div>
  )
}

export default memo(QuickLinks)
