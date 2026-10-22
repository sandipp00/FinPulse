import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  SIGNED_OUT_EVENT,
  getMe,
  loginAccount,
  logoutAccount,
  registerAccount,
} from '../api/finpulse'
import { AuthContext } from '../context/auth-context'

export default function AuthProvider({ children }) {
  const [state, setState] = useState({
    user: null,
    loading: true,
    registrationOpen: true,
    verificationRequired: false,
    emailEnabled: false,
  })

  const applyMe = useCallback((result) => {
    setState((current) => ({
      ...current,
      user: result.user,
      loading: false,
      registrationOpen: result.registration_open,
      verificationRequired: result.verification_required,
      emailEnabled: result.email_enabled,
    }))
  }, [])

  // Find out whether the browser already holds a valid session cookie.
  useEffect(() => {
    let cancelled = false

    getMe()
      .then((result) => {
        if (!cancelled) applyMe(result)
      })
      .catch(() => {
        // The API being down is not "signed out"; the rest of the app reports it.
        if (!cancelled) setState((current) => ({ ...current, loading: false }))
      })

    return () => {
      cancelled = true
    }
  }, [applyMe])

  // Re-read who is signed in (used after confirming an email or resetting a password).
  const refresh = useCallback(() => getMe().then(applyMe).catch(() => {}), [applyMe])

  // Any signed-in request that gets a 401 means the session ended.
  useEffect(() => {
    const onSignedOut = () => setState((current) => ({ ...current, user: null }))
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut)
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut)
  }, [])

  const login = useCallback(async (email, password) => {
    const result = await loginAccount(email, password)
    setState((current) => ({ ...current, user: result.user }))
  }, [])

  const register = useCallback(async (email, password) => {
    const result = await registerAccount(email, password)
    setState((current) => ({ ...current, user: result.user }))
  }, [])

  const logout = useCallback(async () => {
    try {
      await logoutAccount()
    } finally {
      // Even if the call fails, forget the user locally; the cookie is httpOnly
      // and expires on its own.
      setState((current) => ({ ...current, user: null }))
    }
  }, [])

  const value = useMemo(
    () => ({ ...state, login, register, logout, refresh }),
    [state, login, register, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
