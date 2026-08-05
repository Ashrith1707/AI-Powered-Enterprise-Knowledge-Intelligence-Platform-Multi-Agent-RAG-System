import { http } from '@/api/client'

export const searchApi = {
  /** Vector similarity search -> ranked chunks with scores. */
  semantic: ({ query, top_k = 5 }) =>
    http.post('/search', { query, top_k }).then((r) => r.data),

  /**
   * Multi-agent RAG answer -> { answer, citations, confidence, latency_ms,
   * agent_trace }. Pass an AbortSignal to support "stop generation".
   */
  ask: (question, { signal } = {}) =>
    http.post('/ask', { question }, { signal }).then((r) => r.data),
}
