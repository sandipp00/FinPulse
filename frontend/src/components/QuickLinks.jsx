import { memo } from 'react'
import { ArrowUpRight, BarChart3, BookOpen, BriefcaseBusiness, ShieldCheck, TrendingUp } from 'lucide-react'
import { PAGES } from '../lib/pages'
import { ROUTES } from '../lib/routes'
import AppLink from './AppLink'

const LINKS = [
  { route: 'markets', icon: TrendingUp },
  { route: 'analytics', icon: BarChart3 },
  { route: 'risk', icon: ShieldCheck },
  { route: 'research', icon: BookOpen },
  { route: 'portfolio', icon: BriefcaseBusiness },
]

/** The overview's "where to next" panel: one card per page. */
function QuickLinks() {
  return (
    <div className="panel quick-links">
      <div className="panel-heading">
        <div>
          <h2>Explore</h2>
          <p>Jump into the part of FinPulse you need</p>
        </div>
      </div>
      <div className="quick-grid">
        {LINKS.map(({ route, icon: Icon }) => (
          <AppLink key={route} href={ROUTES[route]} className="quick-card">
            <span className="icon-tile"><Icon size={18} /></span>
            <span className="quick-text">
              <strong>{PAGES[route].title}</strong>
              <small>{PAGES[route].blurb}</small>
            </span>
            <ArrowUpRight size={15} className="quick-arrow" />
          </AppLink>
        ))}
      </div>
    </div>
  )
}

export default memo(QuickLinks)
