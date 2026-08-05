import { AnimatePresence, motion } from 'framer-motion'
import {
  Bot, Check, Copy, Gauge, History, ListTree, MessageSquarePlus, MoreHorizontal,
  Pencil, Pin, PinOff, RefreshCcw, ScanSearch, Search, Send, Sparkles, Square,
  Timer, Trash2, X, Zap,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { askStream } from '@/api/chat.api'
import { searchApi } from '@/api/search.api'
import { AgentTimeline } from '@/components/chat/AgentTimeline'
import { ContextInspector } from '@/components/chat/ContextInspector'
import { Markdown } from '@/components/chat/Markdown'
import { DocumentDrawer } from '@/components/documents/DocumentDrawer'
import { ConfirmDialog } from '@/components/shared/States'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Dropdown, DropdownItem, DropdownSeparator } from '@/components/ui/dropdown'
import { useToast } from '@/components/ui/toast'
import { useHealth } from '@/hooks/useAnalytics'
import { useConversations } from '@/hooks/useConversations'
import { cn } from '@/utils/cn'
import { formatRelative } from '@/utils/format'

const STARTERS = [
  'Summarize the key points of the latest uploaded document',
  'What deadlines or dates are mentioned across the documents?',
  'List all financial amounts found in the knowledge base',
]

/* ------------------------- conversation list ------------------------- */

function ChatList({ chats, activeId, onSelect, onNew, onRename, onPin, onDelete }) {
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const q = query.toLowerCase()
    const list = q ? chats.filter((c) => c.title.toLowerCase().includes(q)) : chats
    return [...list.filter((c) => c.pinned), ...list.filter((c) => !c.pinned)]
  }, [chats, query])

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2 p-3">
        <Button className="w-full" size="sm" onClick={onNew}>
          <MessageSquarePlus className="h-4 w-4" /> New chat
        </Button>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats…"
            aria-label="Search conversations"
            className="h-8 w-full rounded-lg border border-edge bg-surface-2/60 pl-8 pr-2 text-xs text-ink placeholder:text-muted focus:border-primary focus:outline-none"
          />
        </div>
      </div>
      <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {filtered.length === 0 && (
          <p className="px-2 py-6 text-center text-xs text-muted">No conversations yet.</p>
        )}
        {filtered.map((chat) => (
          <div
            key={chat.id}
            className={cn(
              'group flex items-center gap-1.5 rounded-lg px-2 py-1.5',
              chat.id === activeId ? 'bg-primary-soft' : 'hover:bg-surface-2',
            )}
          >
            <button onClick={() => onSelect(chat.id)} className="min-w-0 flex-1 text-left" title={chat.title}>
              <p className={cn('truncate text-xs font-medium',
                chat.id === activeId ? 'text-primary' : 'text-ink-2')}>
                {chat.pinned && <Pin className="mr-1 inline h-3 w-3" />}
                {chat.title}
              </p>
              <p className="text-[10px] text-muted">{formatRelative(chat.updated_at)}</p>
            </button>
            <Dropdown
              trigger={
                <button className="rounded p-1 text-muted opacity-0 hover:bg-surface hover:text-ink group-hover:opacity-100"
                  aria-label={`Options for ${chat.title}`}>
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </button>
              }
            >
              <DropdownItem icon={Pencil} onClick={() => onRename(chat)}>Rename</DropdownItem>
              <DropdownItem icon={chat.pinned ? PinOff : Pin} onClick={() => onPin(chat.id)}>
                {chat.pinned ? 'Unpin' : 'Pin'}
              </DropdownItem>
              <DropdownSeparator />
              <DropdownItem icon={Trash2} className="text-danger" onClick={() => onDelete(chat)}>
                Delete
              </DropdownItem>
            </Dropdown>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ----------------------------- messages ----------------------------- */

function AnswerMetaBar({ meta }) {
  if (!meta) return null
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-edge pt-2.5 text-[10px] text-muted">
      <span className="inline-flex items-center gap-1">
        <Gauge className="h-3 w-3" /> confidence {Math.round((meta.confidence ?? 0) * 100)}%
      </span>
      <span className="inline-flex items-center gap-1">
        <Timer className="h-3 w-3" /> {meta.latency_ms} ms
      </span>
      <span className="inline-flex items-center gap-1">
        <ScanSearch className="h-3 w-3" /> {meta.citations?.length ?? 0} sources cited
        {meta.retrieved?.hits && ` · ${meta.retrieved.hits.length} chunks retrieved`}
      </span>
      <span className="inline-flex items-center gap-1">
        <Sparkles className="h-3 w-3" /> Gemini · streamed
      </span>
    </div>
  )
}

function AssistantMessage({ msg, isLatest, onCite, onRegenerate, onInspect }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(msg.content ?? '')
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div>
      <Markdown>{msg.content}</Markdown>

      {msg.meta?.citations?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {msg.meta.citations.map((c) => (
            <button
              key={c.marker}
              onClick={() => onCite(c)}
              title={`${c.document_name}, page ${c.page_number}`}
              className="inline-flex max-w-56 items-center gap-1.5 rounded-full border border-edge bg-surface px-2.5 py-1 text-[11px] text-ink-2 transition-colors hover:border-primary hover:text-primary"
            >
              <span className="font-semibold text-primary">{c.marker}</span>
              <span className="truncate">{c.document_name}</span>
              <span className="shrink-0 text-muted">p.{c.page_number}</span>
            </button>
          ))}
        </div>
      )}

      <AnswerMetaBar meta={msg.meta} />

      <div className="mt-2 flex items-center gap-1">
        <button onClick={copy} aria-label="Copy answer"
          className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-ink">
          {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
        {isLatest && (
          <button onClick={onRegenerate} aria-label="Regenerate answer"
            className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-ink">
            <RefreshCcw className="h-3.5 w-3.5" />
          </button>
        )}
        <button onClick={onInspect} aria-label="Inspect retrieval and agents"
          className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-ink">
          <ListTree className="h-3.5 w-3.5" />
        </button>
        <span className="ml-1 text-[10px] text-muted">
          {new Date(msg.created_at).toLocaleTimeString()}
        </span>
      </div>
    </div>
  )
}

/** Transient bubble while the SSE stream is in flight. */
function LiveMessage({ live, onRetry }) {
  const lastStage = live.stages[live.stages.length - 1]

  if (live.status === 'error' || live.status === 'stopped') {
    return (
      <div className="text-sm">
        <p className={cn(live.status === 'error' ? 'text-danger' : 'text-muted')}>
          {live.status === 'error' ? live.error : 'Generation stopped.'}
        </p>
        <Button size="sm" variant="secondary" className="mt-2" onClick={onRetry}>
          <RefreshCcw className="h-3.5 w-3.5" /> Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="text-sm">
      {live.content ? (
        <>
          <Markdown>{live.content}</Markdown>
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-primary align-text-bottom" />
        </>
      ) : (
        <div className="flex items-center gap-2.5 text-muted">
          <motion.span className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <motion.span key={i} className="h-1.5 w-1.5 rounded-full bg-primary"
                animate={{ opacity: [0.25, 1, 0.25] }}
                transition={{ repeat: Infinity, duration: 1.1, delay: i * 0.18 }} />
            ))}
          </motion.span>
          {lastStage ? lastStage.detail : 'Contacting the RAG pipeline…'}
        </div>
      )}
      {live.stages.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {live.stages.map((s, i) => (
            <motion.span key={i} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
              className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-[10px] text-ink-2">
              <Zap className="h-2.5 w-2.5 text-primary" /> {s.name} {s.ms ? `· ${s.ms}ms` : ''}
            </motion.span>
          ))}
        </div>
      )}
    </div>
  )
}

/* ------------------------------- page ------------------------------- */

export default function AskPage() {
  const { chats, create, appendMessage, rename, togglePin, remove } = useConversations()
  const { data: health } = useHealth()
  const { push } = useToast()
  const [params, setParams] = useSearchParams()

  const [activeId, setActiveId] = useState(null)
  const [input, setInput] = useState(params.get('q') ?? '')
  const [pending, setPending] = useState(false)
  const [live, setLive] = useState(null)     // transient streaming bubble
  const [listOpen, setListOpen] = useState(false)
  const [inspect, setInspect] = useState(null)
  const [inspectTab, setInspectTab] = useState('context')
  const [drawerDoc, setDrawerDoc] = useState(null)
  const [renameTarget, setRenameTarget] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [deleteTarget, setDeleteTarget] = useState(null)

  const abortRef = useRef(null)
  const scrollRef = useRef(null)
  const active = chats.find((c) => c.id === activeId)
  const llmReady = health?.llm_configured

  // Select the most recent conversation once the server list arrives.
  useEffect(() => {
    if (activeId === null && chats.length > 0) setActiveId(chats[0].id)
  }, [chats, activeId])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [active?.messages?.length, live?.content, pending])

  const ask = async (question, chatId) => {
    setPending(true)
    const controller = new AbortController()
    abortRef.current = controller
    setLive({ status: 'pending', content: '', stages: [], question })
    // Real retrieval context for the inspector, fetched in parallel.
    const retrievedPromise = searchApi.semantic({ query: question, top_k: 8 }).catch(() => null)

    try {
      let final = null
      let streamError = null
      await askStream(question, {
        signal: controller.signal,
        conversationId: chatId,
        onStage: (s) => setLive((l) => l && ({ ...l, status: 'streaming', stages: [...l.stages, s] })),
        onToken: (t) => setLive((l) => l && ({ ...l, status: 'streaming', content: l.content + t })),
        onDone: (d) => { final = d },
        onError: (m) => { streamError = m },
      })
      if (streamError) throw new Error(streamError)
      if (!final) throw new Error('The stream ended before an answer arrived.')

      const retrieved = await retrievedPromise
      await appendMessage(chatId, {
        role: 'assistant',
        content: final.answer,
        question,
        meta: {
          citations: final.citations,
          confidence: final.confidence,
          latency_ms: final.latency_ms,
          trace: final.trace,
          retrieved,
        },
      })
      setLive(null)
    } catch (err) {
      const aborted = err.name === 'AbortError' || /abort/i.test(err.message)
      setLive((l) => l && ({ ...l, status: aborted ? 'stopped' : 'error', error: err.message }))
    } finally {
      setPending(false)
      abortRef.current = null
    }
  }

  const send = async (text) => {
    const question = (text ?? input).trim()
    if (!question || pending) return
    try {
      let chatId = activeId
      if (!chatId || !chats.some((c) => c.id === chatId)) {
        chatId = await create()
        setActiveId(chatId)
      }
      await appendMessage(chatId, { role: 'user', content: question })
      setInput('')
      if (params.get('q')) setParams({}, { replace: true })
      await ask(question, chatId)
    } catch (err) {
      push(err.message, 'error')
      setPending(false)
    }
  }

  const regenerate = () => {
    if (!active || pending) return
    const lastUser = [...active.messages].reverse().find((m) => m.role === 'user')
    if (lastUser) ask(lastUser.content, active.id)
  }

  const lastAssistantId = [...(active?.messages ?? [])].reverse()
    .find((m) => m.role === 'assistant')?.id

  return (
    <div className="flex h-[calc(100vh-9.5rem)] overflow-hidden rounded-card border border-edge bg-surface">
      {/* Conversations panel */}
      <aside className={cn(
        'w-60 shrink-0 border-r border-edge bg-surface-2/30',
        'max-lg:absolute max-lg:inset-y-0 max-lg:left-0 max-lg:z-20 max-lg:bg-surface max-lg:shadow-xl',
        !listOpen && 'max-lg:hidden',
      )}>
        <ChatList
          chats={chats}
          activeId={activeId}
          onSelect={(id) => { setActiveId(id); setListOpen(false); setLive(null) }}
          onNew={async () => { setActiveId(await create()); setListOpen(false); setLive(null) }}
          onRename={(c) => { setRenameTarget(c); setRenameValue(c.title) }}
          onPin={togglePin}
          onDelete={(c) => setDeleteTarget(c)}
        />
      </aside>

      {/* Thread */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-edge px-4 py-2.5">
          <Button size="icon" variant="ghost" className="lg:hidden"
            aria-label="Toggle conversation list" onClick={() => setListOpen((o) => !o)}>
            <History className="h-4 w-4" />
          </Button>
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-[#6d5ae0]">
            <Bot className="h-4 w-4 text-white" />
          </div>
          <p className="truncate text-sm font-semibold text-ink">{active?.title ?? 'Ask the knowledge base'}</p>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
          {(!active || active.messages.length === 0) && !live && (
            <div className="mx-auto flex h-full max-w-md flex-col items-center justify-center text-center">
              <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                className="mb-4 rounded-3xl bg-gradient-to-br from-primary to-[#6d5ae0] p-4 shadow-lg">
                <Sparkles className="h-7 w-7 text-white" />
              </motion.div>
              <h2 className="text-lg font-semibold text-ink">Ask your documents anything</h2>
              <p className="mt-1.5 text-sm text-muted">
                Answers stream live from the RAG pipeline with page-level citations,
                and every conversation is saved to your account.
              </p>
              <div className="mt-6 w-full space-y-2">
                {STARTERS.map((s) => (
                  <button key={s} onClick={() => send(s)}
                    className="w-full rounded-xl border border-edge bg-surface px-4 py-2.5 text-left text-xs text-ink-2 transition-colors hover:border-primary hover:text-primary">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="mx-auto max-w-2xl space-y-6">
            <AnimatePresence initial={false}>
              {active?.messages.map((msg) => (
                <motion.div key={msg.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                  className={cn('flex gap-3', msg.role === 'user' && 'justify-end')}>
                  {msg.role === 'assistant' && (
                    <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-[#6d5ae0]">
                      <Bot className="h-4 w-4 text-white" />
                    </div>
                  )}
                  <div className={cn('min-w-0 max-w-[85%] text-sm leading-relaxed',
                    msg.role === 'user'
                      ? 'rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-white'
                      : 'text-ink')}>
                    {msg.role === 'user' ? (
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    ) : (
                      <AssistantMessage
                        msg={msg}
                        isLatest={msg.id === lastAssistantId}
                        onCite={(c) => setDrawerDoc({ id: c.document_id, q: msg.question })}
                        onRegenerate={regenerate}
                        onInspect={() => { setInspect(msg); setInspectTab('context') }}
                      />
                    )}
                  </div>
                </motion.div>
              ))}

              {live && (
                <motion.div key="live" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                  className="flex gap-3">
                  <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-[#6d5ae0]">
                    <Bot className="h-4 w-4 text-white" />
                  </div>
                  <div className="min-w-0 max-w-[85%]">
                    <LiveMessage live={live} onRetry={() => ask(live.question, activeId)} />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Composer */}
        <div className="border-t border-edge p-3 sm:p-4">
          {health && !llmReady && (
            <p className="mb-2 rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">
              {health.llm_detail ??
                'Gemini is not available on the backend — questions will return an error.'}
            </p>
          )}
          <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); send() }}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
              }}
              rows={Math.min(4, Math.max(1, input.split('\n').length))}
              placeholder="Ask a question about your documents… (Enter to send, Shift+Enter for a new line)"
              aria-label="Question input"
              className="max-h-32 flex-1 resize-none rounded-xl border border-edge bg-surface-2/50 px-4 py-2.5 text-sm text-ink placeholder:text-muted focus:border-primary focus:bg-surface focus:outline-none"
            />
            {pending ? (
              <Button type="button" variant="secondary" aria-label="Stop generation"
                onClick={() => abortRef.current?.abort()}>
                <Square className="h-3.5 w-3.5 fill-current" /> Stop
              </Button>
            ) : (
              <Button type="submit" disabled={!input.trim()} aria-label="Send question">
                <Send className="h-4 w-4" />
              </Button>
            )}
          </form>
        </div>
      </div>

      {/* Inspector panel */}
      <AnimatePresence>
        {inspect && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }} animate={{ width: 320, opacity: 1 }} exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="shrink-0 overflow-hidden border-l border-edge bg-surface-2/30 max-xl:absolute max-xl:inset-y-0 max-xl:right-0 max-xl:z-20 max-xl:bg-surface max-xl:shadow-xl"
          >
            <div className="flex h-full w-80 flex-col">
              <div className="flex items-center gap-1 border-b border-edge p-2">
                <button onClick={() => setInspectTab('context')}
                  className={cn('flex-1 rounded-lg px-3 py-1.5 text-xs font-medium',
                    inspectTab === 'context' ? 'bg-primary-soft text-primary' : 'text-muted hover:text-ink')}>
                  Retrieved context
                </button>
                <button onClick={() => setInspectTab('agents')}
                  className={cn('flex-1 rounded-lg px-3 py-1.5 text-xs font-medium',
                    inspectTab === 'agents' ? 'bg-primary-soft text-primary' : 'text-muted hover:text-ink')}>
                  Pipeline timeline
                </button>
                <button onClick={() => setInspect(null)} aria-label="Close inspector"
                  className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-2">
                {inspectTab === 'context' ? (
                  <ContextInspector
                    retrieved={inspect.meta?.retrieved}
                    query={inspect.question}
                    onOpenDocument={(id) => setDrawerDoc({ id, q: inspect.question })}
                  />
                ) : (
                  <div className="p-2">
                    <AgentTimeline trace={inspect.meta?.trace ?? []} />
                  </div>
                )}
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      <DocumentDrawer documentId={drawerDoc?.id} highlight={drawerDoc?.q} onClose={() => setDrawerDoc(null)} />

      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget.id === activeId) setActiveId(null)
          remove(deleteTarget.id)
          setDeleteTarget(null)
          push('Conversation deleted', 'success')
        }}
        title="Delete conversation?"
        description={`"${deleteTarget?.title}" will be permanently removed from your account.`}
      />

      <Dialog
        open={!!renameTarget}
        onClose={() => setRenameTarget(null)}
        title="Rename conversation"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRenameTarget(null)}>Cancel</Button>
            <Button onClick={() => {
              rename(renameTarget.id, renameValue.trim() || renameTarget.title)
              setRenameTarget(null)
            }}>
              Save
            </Button>
          </>
        }
      >
        <Input value={renameValue} onChange={(e) => setRenameValue(e.target.value)}
          aria-label="Conversation title"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              rename(renameTarget.id, renameValue.trim() || renameTarget.title)
              setRenameTarget(null)
            }
          }} />
      </Dialog>
    </div>
  )
}
