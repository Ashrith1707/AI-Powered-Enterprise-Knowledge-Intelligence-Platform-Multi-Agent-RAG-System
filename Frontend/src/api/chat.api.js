import { http } from '@/api/client'

export const chatApi = {
  list: () => http.get('/conversations').then((r) => r.data),
  create: () => http.post('/conversations').then((r) => r.data),
  patch: (id, changes) => http.patch(`/conversations/${id}`, changes).then((r) => r.data),
  remove: (id) => http.delete(`/conversations/${id}`).then((r) => r.data),
  addMessage: (conversationId, message) =>
    http.post(`/conversations/${conversationId}/messages`, message).then((r) => r.data),
}

/**
 * Consumes the SSE stream from POST /api/ask/stream.
 * Calls back with real pipeline stages, real Gemini tokens and the final
 * payload. Abortable via `signal`.
 */
export async function askStream(question, { signal, conversationId, onStage, onToken, onDone, onError }) {
  const { authApi } = await import('@/api/auth.api')
  const session = authApi.getSession()
  const res = await fetch('/api/ask/stream', {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
      ...(session?.accessToken && { Authorization: `Bearer ${session.accessToken}` }),
    },
    body: JSON.stringify({ question, conversation_id: conversationId ?? null }),
  })
  if (!res.ok || !res.headers.get('content-type')?.includes('text/event-stream')) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Streaming failed (${res.status})`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sep
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const eventLine = frame.split('\n').find((l) => l.startsWith('event: '))
      const dataLine = frame.split('\n').find((l) => l.startsWith('data: '))
      if (!dataLine) continue
      const event = eventLine ? eventLine.slice(7).trim() : 'message'
      const data = JSON.parse(dataLine.slice(6))
      if (event === 'stage') onStage?.(data)
      else if (event === 'token') onToken?.(data.text)
      else if (event === 'done') onDone?.(data)
      else if (event === 'error') onError?.(data.message)
    }
  }
}
