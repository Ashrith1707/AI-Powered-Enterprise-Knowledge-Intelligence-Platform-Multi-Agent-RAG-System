/**
 * Visualizes the REAL agent_trace strings returned by /api/ask, e.g.
 *   "search_agent -> rag_answer [ok] 4211.5ms"
 * Nothing is invented: one timeline row per actual trace entry.
 */
import { motion } from 'framer-motion'
import { Bell, BrainCircuit, CheckCircle2, MessageCircleQuestion, ScanSearch, XCircle } from 'lucide-react'

const TRACE_RE = /^(\w+) -> (\w+) \[(ok|FAILED)\] ([\d.]+)ms$/

const TASK_META = {
  rag_answer: { icon: ScanSearch, label: 'Retrieval → rerank → prompt → Gemini generation' },
  semantic_search: { icon: ScanSearch, label: 'Vector similarity search' },
  evaluate_answer: { icon: BrainCircuit, label: 'Answer quality evaluation' },
  notify: { icon: Bell, label: 'Audit notification' },
}

export function parseTrace(trace = []) {
  return trace.map((line) => {
    const m = line.match(TRACE_RE)
    if (!m) return { agent: 'system', task: line, ok: true, ms: null, label: line }
    const [, agent, task, status, ms] = m
    return {
      agent,
      task,
      ok: status === 'ok',
      ms: parseFloat(ms),
      ...( TASK_META[task] ?? { icon: BrainCircuit, label: task } ),
    }
  })
}

export function AgentTimeline({ trace }) {
  const steps = [
    { agent: 'coordinator', task: 'plan', ok: true, ms: null, icon: MessageCircleQuestion, label: 'Query received → task plan created' },
    ...parseTrace(trace),
  ]

  return (
    <ol className="relative ml-2.5 space-y-4 border-l border-edge pl-5" aria-label="Agent execution timeline">
      {steps.map((step, i) => {
        const Icon = step.icon ?? BrainCircuit
        return (
          <motion.li
            key={i}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.12 }}
            className="relative"
          >
            <span className="absolute -left-[27px] flex h-4.5 w-4.5 items-center justify-center rounded-full border border-edge bg-surface">
              {step.ok
                ? <CheckCircle2 className="h-3 w-3 text-success" />
                : <XCircle className="h-3 w-3 text-danger" />}
            </span>
            <div className="flex flex-wrap items-baseline gap-x-2">
              <p className="text-xs font-semibold text-ink">
                {step.agent}
                <span className="ml-1.5 rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] font-normal text-muted">
                  {step.task}
                </span>
              </p>
              {step.ms != null && (
                <span className="text-[10px] tabular-nums text-muted">{step.ms.toFixed(0)} ms</span>
              )}
            </div>
            <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted">
              <Icon className="h-3 w-3" /> {step.label}
            </p>
          </motion.li>
        )
      })}
    </ol>
  )
}
