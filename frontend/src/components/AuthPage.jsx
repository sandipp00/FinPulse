import { useEffect } from 'react'
import { Activity, ArrowLeft } from 'lucide-react'
import { navigate } from '../hooks/useRoute'
import { useAuth } from '../hooks/useAuth'
import { ROUTES } from '../lib/routes'
import AppLink from './AppLink'
import AuthPanel from './AuthPanel'

/** Full-page sign-in / sign-up, separate from the dashboard. */
export default function AuthPage({ route }) {
  const { user, loading } = useAuth()
  const mode = route === 'signup' ? 'register' : 'login'

  useEffect(() => {
    const previous = document.title
    document.title = `${mode === 'register' ? 'Create account' : 'Sign in'} · FinPulse`
    return () => {
      document.title = previous
    }
  }, [mode])

  // Already signed in (or just signed in): go to the paper-trading section.
  useEffect(() => {
    if (user) navigate(ROUTES.home, { replace: true, scrollTo: 'paper-trading' })
  }, [user])

  return (
    <div className="auth-page">
      <header className="auth-page-head">
        <AppLink href={ROUTES.home} className="auth-page-brand" aria-label="FinPulse home">
          <span className="brand-mark"><Activity size={20} strokeWidth={2.5} /></span>
          <span className="brand-name">FinPulse<span>.</span></span>
        </AppLink>
        <AppLink href={ROUTES.home} className="auth-page-back">
          <ArrowLeft size={14} /> Back to dashboard
        </AppLink>
      </header>

      <main className="auth-page-main">
        {loading || user ? (
          <p className="signal-loading">{user ? 'Taking you to your account...' : 'Checking your session...'}</p>
        ) : (
          <AuthPanel
            mode={mode}
            onSwitch={(next) => navigate(next === 'register' ? ROUTES.signup : ROUTES.signin, { replace: true })}
          />
        )}
        <p className="auth-page-note">
          Market data, charts and signals are open to everyone. An account is only needed for paper trading.
        </p>
      </main>
    </div>
  )
}
