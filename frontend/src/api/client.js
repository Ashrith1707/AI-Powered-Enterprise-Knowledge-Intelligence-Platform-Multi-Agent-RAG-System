// ------------------------------------------------------------
// API client: auth-aware fetch wrapper with structured errors.
// Backend errors always arrive as { error: { code, message, details } }.
// On 401 the client tries a token refresh ONCE, then retries.
// ------------------------------------------------------------
const TOKEN_KEY = 'kiq_access_token'
const REFRESH_KEY = 'kiq_refresh_token'

export const tokenStore = {
  get access() { return localStorage.getItem(TOKEN_KEY) },
  get refresh() { return localStorage.getItem(REFRESH_KEY) },
  set({ access_token, refresh_token }) {
    if (access_token) localStorage.setItem(TOKEN_KEY, access_token)
    if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token)
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

export class ApiError extends Error {
  constructor(status, code, message, details = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details || {}
    // AI-specific classification (401 vs 403 vs 404 vs 429 vs network...)
    this.aiErrorCode = this.details?.ai_error_code || null
  }
}

function headers(extra = {}) {
  const h = { ...extra }
  const token = tokenStore.access
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

async function parseError(response) {
  let body = null
  try { body = await response.json() } catch { /* non-JSON */ }
  const err = body?.error || {}
  return new ApiError(
    response.status,
    err.code || `http_${response.status}`,
    err.message || `Request failed (${response.status})`,
    err.details || {},
  )
}

async function rawFetch(url, options) {
  let response
  try {
    response = await fetch(url, options)
  } catch (networkErr) {
    throw new ApiError(0, 'network_error',
      'Could not reach the KnowledgeIQ backend. Is the API server running on port 8001?')
  }
  return response
}

async function request(path, { method = 'GET', body, isForm = false, retry = true } = {}) {
  const url = `/api${path}`
  const options = { method, headers: headers(isForm ? {} : { 'Content-Type': 'application/json' }) }
  if (body !== undefined) options.body = isForm ? body : JSON.stringify(body)

  let response = await rawFetch(url, options)

  if (response.status === 401 && retry && tokenStore.refresh) {
    const refreshed = await tryRefresh()
    if (refreshed) {
      options.headers = headers(isForm ? {} : { 'Content-Type': 'application/json' })
      response = await rawFetch(url, options)
    }
  }

  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return null
  return response.json()
}

async function tryRefresh() {
  try {
    const response = await rawFetch('/api/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: tokenStore.refresh }),
    })
    if (!response.ok) { tokenStore.clear(); return false }
    tokenStore.set(await response.json())
    return true
  } catch {
    tokenStore.clear()
    return false
  }
}

export const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, { method: 'POST', body }),
  patch: (p, body) => request(p, { method: 'PATCH', body }),
  del: (p) => request(p, { method: 'DELETE' }),
  upload: (p, formData) => request(p, { method: 'POST', body: formData, isForm: true }),

  // SSE streaming for Ask AI. Calls handlers per event type.
  async askStream(payload, handlers) {
    const response = await rawFetch('/api/chat/ask/stream', {
      method: 'POST',
      headers: headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(payload),
    })
    if (!response.ok) throw await parseError(response)

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = 'message'

    const dispatch = (event, dataStr) => {
      let data
      try { data = JSON.parse(dataStr) } catch { return }
      const fn = handlers[event] || handlers.onEvent
      if (fn) fn(data)
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() || ''
      for (const block of blocks) {
        let event = 'message'
        const dataLines = []
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
        }
        if (dataLines.length) dispatch(event, dataLines.join('\n'))
        currentEvent = event
      }
    }
    void currentEvent
  },
}
