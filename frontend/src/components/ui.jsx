import { motion } from 'framer-motion'

// ------------------------------------------------------------
// Small shared UI primitives
// ------------------------------------------------------------

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

const STATUS_STYLES = {
  completed: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20',
  processing: 'bg-sky-500/10 text-sky-400 border border-sky-500/20',
  pending: 'bg-slate-500/10 text-slate-400 border border-slate-500/20',
  ocr: 'bg-violet-500/10 text-violet-400 border border-violet-500/20',
  failed: 'bg-red-500/10 text-red-400 border border-red-500/20',
}

export function StatusBadge({ status }) {
  return <span className={`badge ${STATUS_STYLES[status] || STATUS_STYLES.pending}`}>{status}</span>
}

export function StatCard({ label, value, sub, icon, accent = 'text-brand-400' }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="card p-5"
    >
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</div>
        <div className={`text-lg ${accent}`}>{icon}</div>
      </div>
      <div className="mt-2 text-3xl font-bold text-white">{value ?? '—'}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </motion.div>
  )
}

export function ErrorBanner({ error, onDismiss }) {
  if (!error) return null
  const title = error.aiErrorCode ? `AI error (${error.aiErrorCode})` : error.code || 'Error'
  return (
    <div className="mb-4 rounded-lg border border-red-800/60 bg-red-950/40 px-4 py-3 text-sm text-red-200">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="font-semibold">{title}: </span>
          <span>{error.message}</span>
          {error.details?.provider_message && (
            <div className="mt-1 font-mono text-xs text-red-300/70">{error.details.provider_message}</div>
          )}
        </div>
        {onDismiss && (
          <button onClick={onDismiss} className="text-red-400 hover:text-red-200">✕</button>
        )}
      </div>
    </div>
  )
}

export function EmptyState({ icon = '🗂', title, hint, action }) {
  return (
    <div className="card flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
      <div className="text-4xl opacity-60">{icon}</div>
      <div className="text-sm font-semibold text-slate-300">{title}</div>
      {hint && <div className="max-w-md text-xs text-slate-500">{hint}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

export function Spinner({ size = 'h-5 w-5' }) {
  return <div className={`${size} animate-spin rounded-full border-2 border-brand-500 border-t-transparent`} />
}
