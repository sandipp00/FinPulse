import { useCallback, useEffect, useState } from 'react'
import { MailCheck, RefreshCw } from 'lucide-react'
import { resendVerification } from '../api/finpulse'
import { useAuth } from '../hooks/useAuth'

/** Shown instead of the paper account until the signed-in user confirms their email. */
export default function VerifyEmailPanel({ user }) {
  const { refresh, logout } = useAuth()
  const [message, setMessage] = useState(null) // { tone: 'ok' | 'error', text }
  const [busy, setBusy] = useState(false)

  // Confirming in another tab or on a phone should unlock this page on return.
  useEffect(() => {
    const onFocus = () => refresh()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [refresh])

  const resend = useCallback(async () => {
    setBusy(true)
    setMessage(null)
    try {
      const result = await resendVerification()
      setMessage(result.already_verified
        ? { tone: 'ok', text: 'Your email is already confirmed.' }
        : { tone: 'ok', text: `A new link is on its way to ${user.email}.` })
      if (result.already_verified) refresh()
    } catch (err) {
      setMessage({ tone: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }, [refresh, user.email])

  return (
    <div className="auth-card verify-card">
      <h3><MailCheck size={16} /> Check your inbox</h3>
      <p>
        We sent a confirmation link to <strong>{user.email}</strong>. Open it to unlock paper
        trading. The link works once and expires in 24 hours. If you cannot find it, look in spam.
      </p>

      {message && (
        <p className={message.tone === 'ok' ? 'auth-sent' : 'auth-error'} role="status">{message.text}</p>
      )}

      <button className="auth-submit" type="button" onClick={resend} disabled={busy}>
        <RefreshCw size={14} /> {busy ? 'Sending...' : 'Send me a new link'}
      </button>
      <button className="auth-switch" type="button" onClick={refresh}>
        I have confirmed it. Check again
      </button>
      <button className="auth-switch" type="button" onClick={logout}>
        Wrong address? Sign out
      </button>
    </div>
  )
}
