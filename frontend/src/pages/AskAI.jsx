import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import AgentTrace from '../components/AgentTrace'
import CitationList, { VerificationBadge } from '../components/CitationList'
import { ErrorBanner, Spinner } from '../components/ui'

const SUGGESTIONS = [
  'What are the safety requirements for machine maintenance?',
  'How many days of annual leave do employees get?',
  'What is the password policy?',
  'How many documents do I have?',
]

function newAssistantPlaceholder() {
  return {
    role: 'assistant',
    content: '',
    streaming: true,
    trace: { steps: [] },
    citations: [],
    verification: null,
    metrics: null,
    error: null,
  }
}

export default function AskAI() {
  const [conversations, setConversations] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [showTraceFor, setShowTraceFor] = useState(null) // index of message with open trace
  const bottomRef = useRef(null)

  useEffect(() => {
    api.get('/conversations').then(setConversations).catch(() => {})
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const openConversation = async (id) => {
    setError(null)
    try {
      const detail = await api.get(`/conversations/${id}`)
      setConversationId(id)
      setMessages(
        detail.messages.map((m) => ({
          role: m.role,
          content: m.content,
          citations: m.citations || [],
          trace: m.agent_trace || { steps: [] },
          verification: m.agent_trace ? null : null,
          metrics: m.metrics || null,
          streaming: false,
          error: null,
        })),
      )
    } catch (e) { setError(e) }
  }

  const startNewConversation = () => {
    setConversationId(null)
    setMessages([])
    setError(null)
  }

  const ask = async (question) => {
    const q = (question ?? input).trim()
    if (!q || busy) return
    setInput('')
    setBusy(true)
    setError(null)

    const assistantIdx = messages.length + 1
    setMessages((prev) => [...prev, { role: 'user', content: q }, newAssistantPlaceholder()])

    const update = (fn) =>
      setMessages((prev) => prev.map((m, i) => (i === assistantIdx ? fn(m) : m)))

    try {
      await api.askStream(
        { question: q, conversation_id: conversationId },
        {
          trace: (data) => {
            const step = data.step
            update((m) => {
              const steps = [...(m.trace?.steps || [])]
              const existing = steps.findIndex((s) => s.agent === step.agent && s.status === 'running')
              if (step.status === 'running' && existing === -1) steps.push(step)
              else if (existing !== -1) steps[existing] = step
              else steps.push(step)
              return { ...m, trace: { ...m.trace, steps } }
            })
          },
          plan: () => {},
          token: (data) => update((m) => ({ ...m, content: m.content + (data.delta || '') })),
          final: (data) => {
            const r = data.response
            update((m) => ({
              ...m,
              content: r.answer || m.content,
              streaming: false,
              citations: r.citations || [],
              trace: r.trace || m.trace,
              verification: r.verification || null,
              metrics: r.metrics || null,
              insufficient: r.insufficient_evidence,
            }))
            if (r.conversation_id) {
              setConversationId(r.conversation_id)
              api.get('/conversations').then(setConversations).catch(() => {})
            }
          },
          error: (data) => {
            update((m) => ({
              ...m,
              streaming: false,
              error: {
                code: data.code,
                message: data.message,
                details: data.details || {},
                aiErrorCode: data.details?.ai_error_code || data.code,
              },
              content: m.content || '',
            }))
          },
          done: () => {},
        },
      )
    } catch (e) {
      update((m) => ({ ...m, streaming: false, error: e }))
      setError(e)
    } finally {
      setBusy(false)
      update((m) => (m.streaming ? { ...m, streaming: false } : m))
    }
  }

  return (
    <div className="flex h-[calc(100vh-3rem)] gap-4">
      {/* Conversations sidebar */}
      <div className="flex w-64 shrink-0 flex-col">
        <button onClick={startNewConversation} className="btn-primary mb-3 w-full">＋ New conversation</button>
        <div className="flex-1 space-y-1 overflow-y-auto pr-1">
          {conversations.length === 0 && (
            <p className="px-2 py-6 text-center text-xs text-slate-600">No conversations yet.</p>
          )}
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => openConversation(c.id)}
              className={`w-full rounded-lg px-3 py-2 text-left transition ${
                c.id === conversationId ? 'bg-brand-600/15 text-brand-300' : 'text-slate-400 hover:bg-slate-800/60'
              }`}
            >
              <div className="truncate text-xs font-medium">{c.title}</div>
              <div className="text-[10px] text-slate-600">{c.message_count} messages</div>
            </button>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div className="card flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex-1 space-y-5 overflow-y-auto p-6">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600/20 text-2xl">✦</div>
              <div>
                <h2 className="text-lg font-bold text-white">Ask your knowledge base</h2>
                <p className="mt-1 max-w-md text-xs text-slate-500">
                  Eight specialized AI agents plan, retrieve, rerank, compress, generate, verify and
                  cite-check every answer.
                </p>
              </div>
              <div className="grid max-w-lg grid-cols-1 gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => ask(s)} disabled={busy}
                          className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-left text-xs text-slate-400 transition hover:border-brand-600/50 hover:text-slate-200">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) =>
            m.role === 'user' ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[75%] rounded-2xl rounded-br-sm bg-brand-600 px-4 py-2.5 text-sm text-white">
                  {m.content}
                </div>
              </div>
            ) : (
              <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex justify-start">
                <div className="max-w-[85%] min-w-0 space-y-2.5">
                  {m.error && (
                    <div className="rounded-lg border border-red-800/60 bg-red-950/40 px-3 py-2 text-xs text-red-200">
                      <b>{m.error.aiErrorCode || m.error.code}</b>: {m.error.message}
                      {m.error.details?.provider_message && (
                        <div className="mt-1 font-mono text-[10px] text-red-300/70">{m.error.details.provider_message}</div>
                      )}
                    </div>
                  )}

                  {m.content ? (
                    <div className={`rounded-2xl rounded-bl-sm border border-slate-800 bg-slate-900/80 px-4 py-3 text-sm leading-relaxed text-slate-200 ${m.streaming ? 'streaming-caret' : ''}`}>
                      <div className="whitespace-pre-wrap">{m.content}</div>
                      {m.insufficient && (
                        <div className="mt-2 rounded bg-amber-500/10 px-2 py-1 text-[10px] text-amber-400">
                          ⚠ Honest refusal — the knowledge base has no evidence for this question.
                        </div>
                      )}
                    </div>
                  ) : m.streaming ? (
                    <div className="flex items-center gap-2 rounded-2xl rounded-bl-sm border border-slate-800 bg-slate-900/80 px-4 py-3">
                      <Spinner size="h-4 w-4" />
                      <span className="text-xs text-slate-500">Agents are working…</span>
                    </div>
                  ) : null}

                  {/* Live trace while streaming */}
                  {m.streaming && m.trace?.steps?.length > 0 && (
                    <AgentTrace trace={m.trace} />
                  )}

                  {/* Footer controls after completion */}
                  {!m.streaming && (m.trace?.steps?.length > 0 || m.citations?.length > 0 || m.verification) && (
                    <div className="flex flex-wrap items-center gap-2">
                      {m.verification && <VerificationBadge verification={m.verification} />}
                      {m.metrics && (
                        <span className="badge bg-slate-800/80 font-mono text-slate-500"
                              title={`retrieval ${m.metrics.retrieval_latency_ms}ms · generation ${m.metrics.generation_latency_ms}ms · ${m.metrics.chunks_retrieved} chunks retrieved · ${m.metrics.evidences_used} evidences used`}>
                          ⏱ {(m.metrics.total_latency_ms / 1000).toFixed(1)}s · {m.metrics.chunks_retrieved} chunks
                        </span>
                      )}
                      {m.trace?.steps?.length > 0 && (
                        <button
                          onClick={() => setShowTraceFor(showTraceFor === i ? null : i)}
                          className="badge bg-slate-800/80 text-slate-400 transition hover:text-slate-200"
                        >
                          🤖 {showTraceFor === i ? 'Hide' : 'Show'} agent trace ({m.trace.steps.length})
                        </button>
                      )}
                      {m.citations?.length > 0 && (
                        <span className="badge bg-emerald-500/10 text-emerald-400">📎 {m.citations.length} citations</span>
                      )}
                    </div>
                  )}

                  <AnimatePresence>
                    {showTraceFor === i && !m.streaming && (
                      <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                        <AgentTrace trace={m.trace} />
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {!m.streaming && m.citations?.length > 0 && <CitationList citations={m.citations} />}
                </div>
              </motion.div>
            ),
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t border-slate-800 p-4">
          <ErrorBanner error={error} onDismiss={() => setError(null)} />
          <form
            onSubmit={(e) => { e.preventDefault(); ask() }}
            className="flex items-end gap-3"
          >
            <textarea
              className="input max-h-32 min-h-[44px] flex-1 resize-none"
              rows={1}
              placeholder="Ask a question about your documents… (Enter to send, Shift+Enter for newline)"
              value={input}
              disabled={busy}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() }
              }}
            />
            <button className="btn-primary h-11" disabled={busy || !input.trim()}>
              {busy ? <Spinner size="h-4 w-4" /> : '✦ Ask'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
