import { useEffect, useState } from 'react'
import { CheckCircle2, KeyRound, X, XCircle } from 'lucide-react'
import { resetPassword } from '../api/finpulse'
import { ROUTES } from '../lib/routes'
import AppLink from './AppLink'
import { confirmEmailOnce, initialAccountLink, takeLinkFromAddressBar } from '../lib/accountLink'
import { useAuth } from '../hooks/useAuth'

const MIN_PASSWORD = 8

function ConfirmEmail({ token, onDone }) {
  const { refresh } = useAuth()
  const [state, setState] = useState({ status: 'working', text: 'Confirming your email...' })

  useEffect(() => {
    let cancelled = false

    confirmEmailOnce(token)
      .then(() => {
        if (cancelled) return
        setState({ status: 'ok', text: 'Email confirmed. Paper trading is unlocked.' })
        refresh()
      })
      .catch((err) => {
        if (!cancelled) setState({ status: 'error', text: err.message })
      })

    return () => {
      cancelled = true
    }
  }, [token, refresh])

  const Icon = state.status === 'error' ? XCircle : CheckCircle2

  return (
    <div className={`link-banner link-${state.status}`} role="status">
      <Icon size={16} />
      <span>{state.text}</span>
      {state.status !== 'working' && (
        <button onClick={onDone} aria-label="Dismiss"><X size={14} /></button>
      )}
    </div>
  )
}

function ResetPassword({ token, onDone }) {
  const { user, refresh } = useAuth()
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [finished, setFinished] = useState(false)

  const mismatch = repeat.length > 0 && password !== repeat

  // The "sign in below" message has done its job once they have signed in.
  useEffect(() => {
    if (finished && user) onDone()
  }, [finished, user, onDone])

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    if (password !== repeat) return setError('The two passwords do not match.')

    setBusy(true)
    try {
      await resetPassword(token, password)
      setFinished(true)
      refresh() // every old session was revoked, so this page is now signed out
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (finished) {
    return (
      <div className="link-banner link-ok" role="status">
        <CheckCircle2 size={16} />
        <span>
          Password changed, and you were signed out everywhere.{' '}
          <AppLink href={ROUTES.signin} className="link-inline">Sign in with your new password</AppLink>.
        </span>
        <button onClick={onDone} aria-label="Dismiss"><X size={14} /></button>
      </div>
    )
  }

  return (
    <form className="link-banner link-reset" onSubmit={submit}>
      <div className="link-reset-head">
        <KeyRound size={16} />
        <strong>Choose a new password</strong>
        <button type="button" onClick={onDone} aria-label="Cancel"><X size={14} /></button>
      </div>
      <div className="link-reset-fields">
        <input
          type="password"
          placeholder={`New password (${MIN_PASSWORD}+ characters)`}
          autoComplete="new-password"
          aria-label="New password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <input
          type="password"
          placeholder="Repeat it"
          autoComplete="new-password"
          aria-label="Repeat new password"
          value={repeat}
          onChange={(event) => setRepeat(event.target.value)}
        />
        <button
          className="auth-submit"
          type="submit"
          disabled={busy || password.length < MIN_PASSWORD || mismatch}
        >
          {busy ? 'Saving...' : 'Set new password'}
        </button>
      </div>
      {error && <p className="auth-error" role="alert">{error}</p>}
    </form>
  )
}

/**
 * Handles links from emails (#verify=... and #reset=...). They are read when the
 * page loads, and again on `hashchange`: opening a link in a tab where the app is
 * already running only changes the fragment and does not reload the page.
 */
export default function AccountLinkBanner() {
  const [link, setLink] = useState(initialAccountLink)

  useEffect(() => {
    const onHashChange = () => {
      const next = takeLinkFromAddressBar()
      if (next) setLink(next)
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  if (!link) return null
  const done = () => setLink(null)

  // `key` makes a newer link start fresh instead of reusing the old one's state.
  return link.kind === 'verify'
    ? <ConfirmEmail key={link.token} token={link.token} onDone={done} />
    : <ResetPassword key={link.token} token={link.token} onDone={done} />
}
