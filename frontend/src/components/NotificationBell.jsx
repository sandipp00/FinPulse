import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell } from 'lucide-react'
import { useNotifications } from '../hooks/useNotifications'
import NotificationPanel from './NotificationPanel'

/** The top-bar bell: an unread badge, and a dropdown of notifications and price alerts. */
export default function NotificationBell() {
  const { unread, markAllRead } = useNotifications()
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)

  // Whatever was on screen while the panel was open counts as seen once it closes.
  const close = useCallback(() => {
    setOpen(false)
    markAllRead()
  }, [markAllRead])

  useEffect(() => {
    if (!open) return undefined

    const onPointerDown = (event) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) close()
    }
    const onKeyDown = (event) => {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, close])

  return (
    <div className="bell-wrap" ref={wrapRef}>
      <button
        className="icon-button"
        onClick={() => (open ? close() : setOpen(true))}
        aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <Bell size={18} />
        {unread > 0 && <span className="bell-badge">{unread > 9 ? '9+' : unread}</span>}
      </button>
      {open && <NotificationPanel onClose={close} />}
    </div>
  )
}
