import { useContext, useState } from 'react'
import { BellRing, Plus, Trash2, TrendingUp, X } from 'lucide-react'
import { LivePricesContext } from '../context/live-prices-context'
import { useNotifications } from '../hooks/useNotifications'
import { formatPrice, getAssetDetails } from '../lib/format'
import AppLink from './AppLink'

const timeFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
})

const ICONS = { alert: BellRing, signal: TrendingUp }

function Activity({ notifications, onOpen, onClear }) {
  if (notifications.length === 0) {
    return (
      <div className="bell-empty">
        <BellRing size={22} />
        <p>Nothing yet.</p>
        <small>You will see price alerts you set and changes to a daily buy/sell rating here.</small>
      </div>
    )
  }

  return (
    <>
      <ul className="bell-list">
        {notifications.map((note) => {
          const Icon = ICONS[note.kind] ?? BellRing
          return (
            <li key={note.id}>
              <AppLink href={note.href} className={`bell-item ${note.read ? '' : 'bell-item-unread'}`} onClick={onOpen}>
                <span className="bell-item-icon"><Icon size={14} /></span>
                <span className="bell-item-text">
                  {note.text}
                  <small>{timeFormat.format(new Date(note.ts))}</small>
                </span>
              </AppLink>
            </li>
          )
        })}
      </ul>
      <button className="bell-clear" onClick={onClear}><Trash2 size={12} /> Clear all</button>
    </>
  )
}

function Alerts() {
  const { alerts, addAlert, removeAlert } = useNotifications()
  const { ticks, symbols } = useContext(LivePricesContext)

  const [chosen, setChosen] = useState('BTC/USDT')
  const [direction, setDirection] = useState('above')
  const [price, setPrice] = useState('')
  const [error, setError] = useState('')

  const symbol = symbols.includes(chosen) ? chosen : symbols[0] ?? chosen
  const current = ticks[symbol]?.price

  const submit = (event) => {
    event.preventDefault()
    const result = addAlert({ symbol, direction, price }, { ticks, liveSymbols: symbols })
    if (result.ok) {
      setPrice('')
      setError('')
    } else {
      setError(result.error)
    }
  }

  // A quick way to fill the price: one percent past where it is now, in the chosen direction.
  const fillPercent = (percent) => {
    if (current == null) return
    const next = current * (1 + percent / 100)
    setDirection(percent > 0 ? 'above' : 'below')
    setPrice(String(Number(next.toPrecision(6))))
    setError('')
  }

  return (
    <>
      <form className="alert-form" onSubmit={submit} noValidate>
        <div className="alert-row">
          <select aria-label="Asset" value={symbol} onChange={(event) => { setChosen(event.target.value); setError('') }}>
            {symbols.map((item) => <option key={item} value={item}>{item.replace('/USDT', '')}</option>)}
          </select>
          <select aria-label="Direction" value={direction} onChange={(event) => { setDirection(event.target.value); setError('') }}>
            <option value="above">rises to or above</option>
            <option value="below">falls to or below</option>
          </select>
        </div>
        <div className="alert-row">
          <input
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            placeholder="Price (USD)"
            aria-label="Alert price"
            value={price}
            onChange={(event) => { setPrice(event.target.value); setError('') }}
          />
          <button type="submit" className="alert-add" disabled={!price}><Plus size={14} /> Add</button>
        </div>
        <div className="alert-hint">
          <span>{current == null ? 'Waiting for a live price...' : <>Now <b>{formatPrice(current, symbol)}</b></>}</span>
          <span className="alert-quick">
            <button type="button" onClick={() => fillPercent(-1)} disabled={current == null}>-1%</button>
            <button type="button" onClick={() => fillPercent(1)} disabled={current == null}>+1%</button>
          </span>
        </div>
        {error && <p className="alert-error" role="alert">{error}</p>}
      </form>

      <h4 className="alert-heading">Active alerts</h4>
      {alerts.length === 0 ? (
        <p className="alert-none">No active alerts.</p>
      ) : (
        <ul className="alert-list">
          {alerts.map((alert) => (
            <li key={alert.id}>
              <span>
                <b>{getAssetDetails(alert.symbol).name}</b>{' '}
                {alert.direction === 'above' ? 'at or above' : 'at or below'} {formatPrice(alert.price, alert.symbol)}
              </span>
              <button aria-label={`Remove alert for ${alert.symbol}`} onClick={() => removeAlert(alert.id)}><X size={13} /></button>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

/** The bell's dropdown: recent notifications, and the price alerts you have set. */
export default function NotificationPanel({ onClose }) {
  const [tab, setTab] = useState('activity')
  const { notifications, clearNotifications, unread } = useNotifications()

  return (
    <div className="bell-panel" role="dialog" aria-label="Notifications">
      <div className="bell-tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'activity'} className={tab === 'activity' ? 'bell-tab-on' : ''} onClick={() => setTab('activity')}>
          Activity{unread > 0 && <span className="bell-count">{unread}</span>}
        </button>
        <button role="tab" aria-selected={tab === 'alerts'} className={tab === 'alerts' ? 'bell-tab-on' : ''} onClick={() => setTab('alerts')}>
          Price alerts
        </button>
      </div>

      <div className="bell-body">
        {tab === 'activity'
          ? <Activity notifications={notifications} onOpen={onClose} onClear={clearNotifications} />
          : <Alerts />}
      </div>

      <p className="bell-foot">
        Saved in this browser only. Alerts are checked while FinPulse is open in a tab; they cannot
        reach you when it is closed.
      </p>
    </div>
  )
}
