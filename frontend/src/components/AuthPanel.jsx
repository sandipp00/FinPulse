import { useState } from 'react'
import { LogIn, Mail, UserPlus } from 'lucide-react'
import { forgotPassword } from '../api/finpulse'
import { useAuth } from '../hooks/useAuth'

const MIN_PASSWORD = 8

const TITLES = {
  login: 'Sign in',
  register: 'Create your account',
  forgot: 'Reset your password',
}

export default function AuthPanel() {
  const { login, register, registrationOpen, emailEnabled, verificationRequired } = useAuth()
  const [mode, setMode] = useState('login') // 'login' | 'register' | 'forgot'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [sent, setSent] = useState('')
  const [busy, setBusy] = useState(false)

  const creating = mode === 'register'
  const forgot = mode === 'forgot'
  const tooShort = creating && password.length > 0 && password.length < MIN_PASSWORD

  const switchTo = (next) => {
    setMode(next)
    setError('')
    setSent('')
  }

  const submit = async (event) => {
    event.preventDefault()
    setError('')
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
      // On a successful sign-in the provider swaps this panel out anyway.
      setBusy(false)
    }
  }

  return (
    <form className="auth-card" onSubmit={submit} noValidate>
      <h3>{TITLES[mode]}</h3>
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

      {mode === 'login' && emailEnabled && (
        <button className="auth-switch" type="button" onClick={() => switchTo('forgot')}>
          Forgot your password?
        </button>
      )}

      {forgot ? (
        <button className="auth-switch" type="button" onClick={() => switchTo('login')}>
          Back to sign in
        </button>
      ) : registrationOpen || creating ? (
        <button className="auth-switch" type="button" onClick={() => switchTo(creating ? 'login' : 'register')}>
          {creating ? 'Already have an account? Sign in' : 'New here? Create an account'}
        </button>
      ) : (
        <p className="auth-closed">New registrations are closed on this server.</p>
      )}
    </form>
  )
}
