import { useCallback, useEffect, useState } from 'react'
import { LogIn, LogOut, Mail, RefreshCw } from 'lucide-react'
import { forgotPassword, getHealth, getLiveStatus } from '../api/finpulse'
import AppLink from '../components/AppLink'
import { useAuth } from '../hooks/useAuth'
import { ROUTES } from '../lib/routes'

function Row({ label, value, tone }) {
  return (
    <div className="setting-row">
      <span>{label}</span>
      <strong className={tone ? `tone-${tone}` : ''}>{value}</strong>
    </div>
  )
}

function useConnectionInfo() {
  const [info, setInfo] = useState({ loading: true, health: null, live: null, error: '' })

  const load = useCallback(() => (
    Promise.all([getHealth(), getLiveStatus()])
      .then(([health, live]) => ({ loading: false, health, live, error: '' }))
      .catch((err) => ({ loading: false, health: null, live: null, error: err.message }))
  ), [])

  useEffect(() => {
    let cancelled = false
    load().then((next) => {
      if (!cancelled) setInfo(next)
    })
    return () => {
      cancelled = true
    }
  }, [load])

  const refresh = () => {
    setInfo((current) => ({ ...current, loading: true }))
    load().then(setInfo)
  }

  return { ...info, refresh }
}

function AccountCard() {
  const { user, emailEnabled, verificationRequired, logout } = useAuth()
  const [message, setMessage] = useState(null) // { tone, text }
  const [busy, setBusy] = useState(false)

  if (!user) {
    return (
      <div className="panel settings-card">
        <h2>Account</h2>
        <p>You are not signed in. Market data and charts are open to everyone; an account is only needed for paper trading.</p>
        <div className="settings-actions">
          <AppLink href={ROUTES.signin} className="auth-submit"><LogIn size={14} /> Sign in</AppLink>
          <AppLink href={ROUTES.signup} className="auth-secondary">Create account</AppLink>
        </div>
      </div>
    )
  }

  const sendReset = async () => {
    setBusy(true)
    setMessage(null)
    try {
      const result = await forgotPassword(user.email)
      setMessage({ tone: 'ok', text: result.message })
    } catch (err) {
      setMessage({ tone: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel settings-card">
      <h2>Account</h2>
      <Row label="Email" value={user.email} />
      <Row
        label="Email confirmed"
        value={user.email_verified ? 'Yes' : verificationRequired ? 'Not yet' : 'Not required on this server'}
        tone={user.email_verified ? 'up' : undefined}
      />
      <div className="settings-actions">
        {emailEnabled && (
          <button className="auth-secondary" onClick={sendReset} disabled={busy}>
            <Mail size={14} /> {busy ? 'Sending...' : 'Email me a password reset link'}
          </button>
        )}
        <button className="auth-secondary settings-signout" onClick={logout}>
          <LogOut size={14} /> Sign out
        </button>
      </div>
      {message && (
        <p className={`ticket-message ticket-${message.tone}`} role="status">{message.text}</p>
      )}
      {!emailEnabled && (
        <p className="settings-hint">
          Changing a password by email needs email to be set up on this server. The person running it can use the
          admin commands instead.
        </p>
      )}
    </div>
  )
}

function ConnectionCard({ liveStatus }) {
  const { loading, health, live, error, refresh } = useConnectionInfo()

  return (
    <div className="panel settings-card">
      <div className="settings-card-head">
        <h2>Connection</h2>
        <button className="paper-reset" onClick={refresh} disabled={loading}>
          <RefreshCw size={13} /> {loading ? 'Checking...' : 'Refresh'}
        </button>
      </div>

      {error ? (
        <p className="signal-error">Could not reach the API: {error}</p>
      ) : (
        <>
          <Row label="API" value={health ? 'Healthy' : '…'} tone={health ? 'up' : undefined} />
          <Row label="Stored price records" value={health ? health.records.toLocaleString('en-US') : '…'} />
          <Row
            label="Live price feed (this page)"
            value={{ live: 'Connected', connecting: 'Connecting…', reconnecting: 'Reconnecting…', offline: 'Exchange offline' }[liveStatus]}
            tone={liveStatus === 'live' ? 'up' : undefined}
          />
          <Row
            label="Live feed (server)"
            value={!live ? '…' : !live.enabled ? 'Turned off' : live.connected ? 'Connected' : 'Disconnected'}
            tone={live?.connected ? 'up' : undefined}
          />
          {live?.source && <Row label="Exchange endpoint" value={live.source.replace(/^wss:\/\//, '')} />}
          {live?.symbols && <Row label="Streaming" value={live.symbols.map((s) => s.replace('/USDT', '')).join(', ')} />}
          {live?.last_error && <p className="settings-hint">Last feed error: {live.last_error}</p>}
        </>
      )}
    </div>
  )
}

function AboutCard() {
  return (
    <div className="panel settings-card">
      <h2>About</h2>
      <Row label="Data" value="Binance (crypto; live gold and silver futures), Yahoo Finance (stocks, indices, COMEX metals; stored)" />
      <Row label="Paper trading" value="Virtual money, live prices, simulated fees" />
      <Row label="Signals" value="Educational. Not investment advice." />
      <div className="settings-actions">
        <a className="auth-secondary" href="https://github.com/sandipp00/FinPulse" target="_blank" rel="noopener noreferrer">
          Source code on GitHub
        </a>
      </div>
    </div>
  )
}

export default function SettingsPage({ liveStatus }) {
  return (
    <div className="settings-grid">
      <AccountCard />
      <ConnectionCard liveStatus={liveStatus} />
      <AboutCard />
    </div>
  )
}
