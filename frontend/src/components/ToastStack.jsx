import { useEffect } from 'react'
import { BellRing, TrendingUp, X } from 'lucide-react'
import { useNotifications } from '../hooks/useNotifications'
import AppLink from './AppLink'

const TOAST_MS = 8000
const ICONS = { alert: BellRing, signal: TrendingUp }

function Toast({ toast, onDismiss }) {
  const Icon = ICONS[toast.kind] ?? BellRing

  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), TOAST_MS)
    return () => clearTimeout(timer)
  }, [toast.id, onDismiss])

  return (
    <div className="toast" role="status">
      <span className="toast-icon"><Icon size={15} /></span>
      <AppLink href={toast.href} className="toast-text" onClick={() => onDismiss(toast.id)}>{toast.text}</AppLink>
      <button className="toast-close" aria-label="Dismiss" onClick={() => onDismiss(toast.id)}><X size={14} /></button>
    </div>
  )
}

/** Brief pop-ups for new notifications, so an alert is noticed even with the bell closed. */
export default function ToastStack() {
  const { toasts, dismissToast } = useNotifications()
  if (toasts.length === 0) return null

  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map((toast) => <Toast key={toast.id} toast={toast} onDismiss={dismissToast} />)}
    </div>
  )
}
