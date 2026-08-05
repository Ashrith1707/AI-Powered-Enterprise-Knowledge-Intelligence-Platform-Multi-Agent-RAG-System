/**
 * Single axios instance for the whole app.
 * - Attaches the JWT access token
 * - On 401: refreshes via the rotating refresh token and retries ONCE;
 *   if refresh fails the session is cleared and the user returns to /login
 * - Normalizes every error to a readable message (FastAPI puts it in `detail`)
 */
import axios from 'axios'
import { authApi } from '@/api/auth.api'

export const http = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

http.interceptors.request.use((config) => {
  const session = authApi.getSession()
  if (session?.accessToken) config.headers.Authorization = `Bearer ${session.accessToken}`
  return config
})

let refreshing = null

async function refreshSession(session) {
  // Deduplicate concurrent refreshes: all 401s share one refresh call.
  refreshing ??= axios
    .post('/api/auth/refresh', { refresh_token: session.refreshToken })
    .then((r) => authApi.updateStoredSession(r.data))
    .finally(() => { refreshing = null })
  return refreshing
}

http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { response, config } = error
    const session = authApi.getSession()

    if (response?.status === 401 && session?.refreshToken && !config._retried
        && !config.url.startsWith('/auth/')) {
      try {
        const fresh = await refreshSession(session)
        config._retried = true
        config.headers.Authorization = `Bearer ${fresh.accessToken}`
        return http(config)
      } catch {
        authApi.clear()
        window.location.assign('/login')
        return Promise.reject(new Error('Session expired — please sign in again.'))
      }
    }

    const detail = response?.data?.detail
    const message =
      (typeof detail === 'string' && detail) ||
      (Array.isArray(detail) && detail[0]?.msg) ||
      error.message ||
      'Something went wrong'
    return Promise.reject(new Error(message))
  },
)
