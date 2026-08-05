/**
 * Real JWT authentication against the FastAPI backend.
 * Session shape: { user, accessToken, refreshToken } in localStorage.
 * The axios interceptors (client.js) attach the access token and transparently
 * refresh it on 401 using the rotating refresh token.
 */
import { http } from '@/api/client'

const SESSION_KEY = 'eki.session'

function saveSession(tokens) {
  const session = {
    user: {
      ...tokens.user,
      name: tokens.user.full_name || tokens.user.email.split('@')[0],
      initials: tokens.user.email.slice(0, 2).toUpperCase(),
    },
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
  }
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
  return session
}

export const authApi = {
  register: ({ email, password, fullName }) =>
    http.post('/auth/register', { email, password, full_name: fullName ?? '' })
      .then((r) => saveSession(r.data)),

  login: ({ email, password, rememberMe }) =>
    http.post('/auth/login', { email, password, remember_me: !!rememberMe })
      .then((r) => saveSession(r.data)),

  me: () => http.get('/auth/me').then((r) => r.data),

  async logout() {
    const session = this.getSession()
    localStorage.removeItem(SESSION_KEY)
    if (session?.refreshToken) {
      // Best effort — revoke the refresh token server-side.
      try { await http.post('/auth/logout', { refresh_token: session.refreshToken }) } catch { /* already signed out */ }
    }
  },

  getSession() {
    try {
      const s = JSON.parse(localStorage.getItem(SESSION_KEY))
      return s?.accessToken ? s : null   // discard old demo-mode sessions
    } catch {
      return null
    }
  },

  updateStoredSession: saveSession,
  clear: () => localStorage.removeItem(SESSION_KEY),
}
