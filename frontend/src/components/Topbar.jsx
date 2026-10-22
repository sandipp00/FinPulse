import { memo } from 'react'
import { Bell, LogIn, LogOut, Menu, Search } from 'lucide-react'
import { ROUTES } from '../lib/routes'
import AppLink from './AppLink'

function Topbar({ pageTitle, search, onSearch, onOpenMenu, user, onLogout }) {
  return (
    <header className="topbar">
      <div className="flex min-w-0 items-center gap-3">
        <button className="mobile-menu" onClick={onOpenMenu} aria-label="Open menu">
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
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Search assets..."
            aria-label="Search assets"
          />
          <kbd>⌘ K</kbd>
        </label>
        <button className="icon-button" aria-label="Notifications">
          <Bell size={18} /><span className="notification-dot" />
        </button>
        {user ? (
          <>
            <span className="top-user" title={user.email}>{user.email}</span>
            <div className="top-avatar" aria-hidden="true">{user.email.slice(0, 2).toUpperCase()}</div>
            <button className="icon-button" onClick={onLogout} aria-label="Sign out" title="Sign out">
              <LogOut size={17} />
            </button>
          </>
        ) : (
          <AppLink href={ROUTES.signin} className="topbar-signin">
            <LogIn size={14} /> Sign in
          </AppLink>
        )}
      </div>
    </header>
  )
}

export default memo(Topbar)
