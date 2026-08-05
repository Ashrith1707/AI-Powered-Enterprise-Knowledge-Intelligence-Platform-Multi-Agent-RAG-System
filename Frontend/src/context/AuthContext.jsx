import { createContext, useContext, useState } from 'react'
import { authApi } from '@/api/auth.api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => authApi.getSession())

  const login = async (credentials) => {
    const s = await authApi.login(credentials)
    setSession(s)
    return s
  }

  const register = async (details) => {
    const s = await authApi.register(details)
    setSession(s)
    return s
  }

  const logout = () => {
    authApi.logout()   // revokes the refresh token server-side, best effort
    setSession(null)
  }

  return (
    <AuthContext.Provider value={{ session, user: session?.user ?? null, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
