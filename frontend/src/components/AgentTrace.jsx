import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'

// ------------------------------------------------------------
// AI Agent Trace — safe execution summaries only.
// Shows per-agent status, duration and stats. Never displays
// hidden chain-of-thought or raw prompts.
// ------------------------------------------------------------

const AGENT_LABELS = {
  planner: { label: 'Planner', icon: '🧭' },
  retriever: { label: 'Retriever', icon: '🔎' },
  metadata: { label: 'Metadata', icon: '🏷' },
  reranker: { label: 'Reranker', icon: '📊' },
  compressor: { label: 'Compression', icon: '🗜' },
  answer_generator: { label: 'Generator', icon: '✍️' },
  verifier: { label: 'Verification', icon: '✅' },
  citation_validator: { label: 'Citation Validation', icon: '📎' },
}

const STATUS_STYLE = {
  completed: { dot: 'bg-emerald-400', text: 'text-emerald-400', label: 'completed' },
  running: { dot: 'bg-sky-400 animate-pulse', text: 'text-sky-400', label: 'running' },
  skipped: { dot: 'bg-slate-500', text: 'text-slate-500', label: 'skipped' },
  failed: { dot: 'bg-red-400', text: 'text-red-400', label: 'failed' },
  pending: { dot: 'bg-slate-600', text: 'text-slate-500', label: 'pending' },
}

function fmtStats(stats) {
  if (!stats) return []
  return Object.entries(stats)
    .filter(([, v]) => v !== null && v !== undefined && typeof v !== 'object')
    .slice(0, 8)
    .map(([k, v]) => [k.replace(/_/g, ' '), typeof v === 'number' && !Number.isInteger(v) ? v.toFixed(2) : String(v)])
}

export function TraceStep({ step, isLast }) {
  const [open, setOpen] = useState(false)
  const meta = AGENT_LABELS[step.agent] || { label: step.agent, icon: '⚙' }
  const st = STATUS_STYLE[step.status] || STATUS_STYLE.pending

  return (
    <div className="relative pl-8">
      {!isLast && <div className="absolute left-[9px] top-5 h-full w-px bg-slate-800" />}
      <div className={`absolute left-0 top-1.5 h-[19px] w-[19px] rounded-full border-2 border-slate-800 bg-slate-900 flex items-center justify-center`}>
        <div className={`h-2 w-2 rounded-full ${st.dot}`} />
      </div>

      <button
        onClick={() => setOpen(!open)}
        className="group w-full rounded-lg px-2 py-1.5 text-left transition hover:bg-slate-800/50"
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm">
            <span>{meta.icon}</span>
            <span className="font-medium text-slate-200">{meta.label}</span>
            <span className={`text-[10px] uppercase tracking-wider ${st.text}`}>{st.label}</span>
          </div>
          <div className="flex items-center gap-2">
            {step.duration_ms > 0 && (
              <span className="font-mono text-[10px] text-slate-500">{step.duration_ms.toFixed(0)}ms</span>
            )}
            <span className="text-[10px] text-slate-600 group-hover:text-slate-400">{open ? '▲' : '▼'}</span>
          </div>
        </div>
        {step.summary && !open && (
          <div className="mt-0.5 truncate pl-7 text-xs text-slate-500">{step.summary}</div>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="mx-2 mb-2 ml-7 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              {step.summary && <p className="text-xs leading-relaxed text-slate-300">{step.summary}</p>}
              {step.error && (
                <p className="mt-1 rounded bg-red-950/50 px-2 py-1 font-mono text-[11px] text-red-300">
                  {step.error.code}: {step.error.message}
                </p>
              )}
              {fmtStats(step.stats).length > 0 && (
                <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
                  {fmtStats(step.stats).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-2 text-[11px]">
                      <span className="text-slate-500">{k}</span>
                      <span className="truncate font-mono text-slate-300">{v}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function AgentTrace({ trace, className = '' }) {
  const [open, setOpen] = useState(true)
  if (!trace || !trace.steps || trace.steps.length === 0) return null

  return (
    <div className={`card overflow-hidden ${className}`}>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between border-b border-slate-800 px-4 py-2.5"
      >
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
          <span>🤖</span> Agent Execution Trace
          <span className="badge bg-slate-800 text-slate-400">{trace.steps.length} steps</span>
        </div>
        <div className="flex items-center gap-3">
          {trace.total_duration_ms > 0 && (
            <span className="font-mono text-[10px] text-slate-500">
              total {trace.total_duration_ms.toFixed(0)}ms
            </span>
          )}
          <span className="text-xs text-slate-500">{open ? '▲' : '▼'}</span>
        </div>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }}
            className="overflow-hidden"
          >
            <div className="space-y-0.5 p-3">
              {trace.steps.map((step, i) => (
                <TraceStep key={`${step.agent}-${i}`} step={step} isLast={i === trace.steps.length - 1} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
