/**
 * Retrieved-context panel. The chunks and scores come from a real call to
 * /api/search with the same question — the identical dense retriever the RAG
 * pipeline uses (top-8 before reranking). Labeled as such in the UI.
 */
import { motion } from 'framer-motion'
import { FileText } from 'lucide-react'
import { highlightTerms } from '@/utils/highlight'

export function ContextInspector({ retrieved, query, onOpenDocument }) {
  if (!retrieved?.hits?.length) {
    return <p className="p-4 text-xs text-muted">No chunks were retrieved for this query.</p>
  }
  return (
    <div className="space-y-2.5 p-1">
      <p className="px-2 text-[11px] leading-relaxed text-muted">
        Top-{retrieved.hits.length} chunks from the dense retriever (FAISS cosine),
        fetched in {retrieved.latency_ms} ms — the same candidates the RAG pipeline reranks.
      </p>
      {retrieved.hits.map((hit, i) => (
        <motion.button
          key={hit.chunk_id}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05 }}
          onClick={() => onOpenDocument(hit.document_id)}
          className="block w-full rounded-xl border border-edge bg-surface p-3 text-left transition-colors hover:border-primary/50"
        >
          <div className="mb-1.5 flex items-center gap-2">
            <FileText className="h-3.5 w-3.5 shrink-0 text-primary" />
            <span className="min-w-0 flex-1 truncate text-xs font-medium text-ink">{hit.document_name}</span>
            <span className="shrink-0 rounded-full bg-primary-soft px-2 py-0.5 text-[10px] font-semibold tabular-nums text-primary">
              {hit.score.toFixed(3)}
            </span>
          </div>
          <p className="line-clamp-3 text-[11px] leading-relaxed text-ink-2">
            {highlightTerms(hit.snippet, query)}
          </p>
          <p className="mt-1.5 text-[10px] text-muted">page {hit.page_number} · chunk #{hit.chunk_id}</p>
        </motion.button>
      ))}
    </div>
  )
}
