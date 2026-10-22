import { useState } from 'react'
import { LogIn, Mail, UserPlus } from 'lucide-react'
import { forgotPassword } from '../api/finpulse'
import { useAuth } from '../hooks/useAuth'

const MIN_PASSWORD = 8

/**
 * The sign-in / sign-up / forgot-password form.
 *   mode      'login' | 'register', decided by the page URL
 *   onSwitch  asked to move between the two (the page changes the URL)
 * "Forgot password" is a third state kept here, since it has no page of its own.
 */
export default function AuthPanel({ mode, onSwitch }) {
  const { login, register, registrationOpen, emailEnabled, verificationRequired } = useAuth()
  const [forgot, setForgot] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [sent, setSent] = useState('')
  const [busy, setBusy] = useState(false)

  const creating = mode === 'register'
  const tooShort = creating && password.length > 0 && password.length < MIN_PASSWORD

  const title = forgot ? 'Reset your password' : creating ? 'Create your account' : 'Sign in'

  const clearMessages = () => {
    setError('')
    setSent('')
  }

  const switchMode = (next) => {
    clearMessages()
    setForgot(false)
    onSwitch(next)
  }

  const submit = async (event) => {
    event.preventDefault()
    clearMessages()
    setBusy(true)
    try {
      if (forgot) {
        const result = await forgotPassword(email)
        setSent(result.message)
      } else {
        await (creating ? register : login)(email, password)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      // On a successful sign-in the page redirects away, so there is nothing to reset.
      setBusy(false)
    }
  }

  return (
    <form className="auth-card" onSubmit={submit} noValidate>
      <h3>{title}</h3>
      <p>
        {forgot
          ? 'Enter the email you signed up with and we will send a link to choose a new password.'
          : 'Paper trading keeps a separate virtual account for each person. No real money, and no card or personal details beyond an email.'}
      </p>

      <label className="auth-field">
        <span>Email</span>
        <input
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoFocus
        />
      </label>

      {!forgot && (
        <label className="auth-field">
          <span>Password</span>
          <input
            type="password"
            autoComplete={creating ? 'new-password' : 'current-password'}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          {creating && (
            <small className={tooShort ? 'auth-hint-bad' : ''}>
              At least {MIN_PASSWORD} characters. A few unrelated words make a strong password.
              {verificationRequired && ' We will email you a link to confirm your address.'}
            </small>
          )}
        </label>
      )}

      {error && <p className="auth-error" role="alert">{error}</p>}
      {sent && <p className="auth-sent" role="status"><Mail size={13} /> {sent}</p>}

      <button
        className="auth-submit"
        type="submit"
        disabled={busy || !email || (!forgot && !password)}
      >
        {forgot ? <Mail size={14} /> : creating ? <UserPlus size={14} /> : <LogIn size={14} />}
        {busy ? 'Please wait...' : forgot ? 'Email me a reset link' : creating ? 'Create account' : 'Sign in'}
      </button>

      {!forgot && !creating && emailEnabled && (
        <button className="auth-switch" type="button" onClick={() => { clearMessages(); setForgot(true) }}>
          Forgot your password?
        </button>
      )}

      {forgot ? (
        <button className="auth-switch" type="button" onClick={() => { clearMessages(); setForgot(false) }}>
          Back to sign in
        </button>
      ) : registrationOpen || creating ? (
        <button className="auth-switch" type="button" onClick={() => switchMode(creating ? 'login' : 'register')}>
          {creating ? 'Already have an account? Sign in' : 'New here? Create an account'}
        </button>
      ) : (
        <p className="auth-closed">New registrations are closed on this server.</p>
      )}
    </form>
  )
}
