import { motion } from 'framer-motion'

// ------------------------------------------------------------
// Citations — every citation maps to a real retrieved chunk
// (document + page range + quote), validated by the
// Citation Validation Agent on the backend.
// ------------------------------------------------------------

function pageLabel(c) {
  if (!c.page_start) return ''
  return c.page_start === c.page_end ? `p. ${c.page_start}` : `pp. ${c.page_start}–${c.page_end}`
}

export default function CitationList({ citations, compact = false }) {
  if (!citations || citations.length === 0) return null

  return (
    <div className={compact ? 'space-y-1.5' : 'space-y-2'}>
      {!compact && (
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          📎 Sources ({citations.length})
        </div>
      )}
      {citations.map((c, i) => (
        <motion.div
          key={c.citation_id || i}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.04 }}
          className="rounded-lg border border-slate-800 bg-slate-950/60 p-3"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-xs font-semibold text-slate-200">
                <span className="mr-1.5 inline-flex h-4 w-4 items-center justify-center rounded bg-brand-600/30 text-[9px] font-bold text-brand-300">
                  {c.citation_id?.replace('C', '') || i + 1}
                </span>
                {c.document_title || c.filename}
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[10px] text-slate-500">
                <span>{pageLabel(c)}</span>
                <span>·</span>
                <span className="font-mono">chunk #{c.chunk_id}</span>
              </div>
            </div>
          </div>
          {c.quote && !compact && (
            <p className="mt-2 line-clamp-3 border-l-2 border-brand-600/40 pl-2 text-[11px] italic leading-relaxed text-slate-400">
              “{c.quote}”
            </p>
          )}
        </motion.div>
      ))}
    </div>
  )
}

export function VerificationBadge({ verification }) {
  if (!verification) return null
  const ok = verification.verified
  const pct = Math.round((verification.confidence || 0) * 100)
  return (
    <span
      className={`badge ${ok ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'}`}
      title={`Method: ${verification.method || 'n/a'} · unsupported claims: ${(verification.unsupported_claims || []).length}`}
    >
      {ok ? '✓' : '⚠'} {ok ? 'Verified' : 'Unverified'} · {pct}%
    </span>
  )
}
