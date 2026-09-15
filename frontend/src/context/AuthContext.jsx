import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, tokenStore } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const loadMe = useCallback(async () => {
    if (!tokenStore.access) { setUser(null); setLoading(false); return null }
    try {
      const me = await api.get('/auth/me')
      setUser(me)
      return me
    } catch {
      tokenStore.clear()
      setUser(null)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadMe() }, [loadMe])

  const login = useCallback(async (email, password) => {
    const tokens = await api.post('/auth/login', { email, password })
    tokenStore.set(tokens)
    return loadMe()
  }, [loadMe])

  const register = useCallback(async (email, password, fullName) => {
    await api.post('/auth/register', { email, password, full_name: fullName })
    const tokens = await api.post('/auth/login', { email, password })
    tokenStore.set(tokens)
    return loadMe()
  }, [loadMe])

  const logout = useCallback(async () => {
    try { await api.post('/auth/logout') } catch { /* best effort */ }
    tokenStore.clear()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, reload: loadMe }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
