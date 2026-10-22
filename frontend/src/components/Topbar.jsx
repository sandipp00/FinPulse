import { memo } from 'react'
import { Bell, Menu, Search } from 'lucide-react'

function Topbar({ pageTitle, search, onSearch, onOpenMenu }) {
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
        <div className="top-avatar">SP</div>
      </div>
    </header>
  )
}

export default memo(Topbar)
