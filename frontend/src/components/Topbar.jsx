import { memo, useEffect, useRef } from 'react'
import { LogIn, LogOut, Menu, Search } from 'lucide-react'
import { ROUTES } from '../lib/routes'
import AppLink from './AppLink'
import NotificationBell from './NotificationBell'

// The shortcut is Cmd+K on a Mac and Ctrl+K everywhere else, and the hint should say which.
const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/i.test(navigator.platform || navigator.userAgent)
const SHORTCUT_HINT = IS_MAC ? '⌘ K' : 'Ctrl K'

function Topbar({ pageTitle, search, onSearch, onOpenMenu, user, onLogout }) {
  const searchRef = useRef(null)

  // Cmd/Ctrl+K jumps to the search box from anywhere on the page. The browser has its own
  // meaning for the key (Chrome and Firefox focus their search bar), so take it over.
  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        searchRef.current?.focus()
        searchRef.current?.select()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  // Escape clears the search; pressing it again (or with nothing typed) leaves the box.
  const onSearchKeyDown = (event) => {
    if (event.key !== 'Escape') return
    if (search) onSearch('')
    else event.currentTarget.blur()
  }

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
            ref={searchRef}
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            onKeyDown={onSearchKeyDown}
            placeholder="Search assets..."
            aria-label="Search assets"
            aria-keyshortcuts={IS_MAC ? 'Meta+K' : 'Control+K'}
          />
          <kbd>{SHORTCUT_HINT}</kbd>
        </label>
        <NotificationBell />
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
