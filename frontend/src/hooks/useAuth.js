import { useContext } from 'react'
import { AuthContext } from '../context/auth-context'

/** { user, loading, registrationOpen, verificationRequired, emailEnabled, login, register, logout, refresh, resetEpoch, markPasswordReset } */
export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}
