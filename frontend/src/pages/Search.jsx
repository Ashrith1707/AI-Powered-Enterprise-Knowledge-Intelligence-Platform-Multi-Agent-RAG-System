import { motion } from 'framer-motion'
import { useState } from 'react'
import { api } from '../api/client'
import { EmptyState, ErrorBanner, PageHeader, Spinner } from '../components/ui'

const MODES = [
  { id: 'hybrid', label: 'Hybrid', hint: 'vector + keyword (RRF fusion)' },
  { id: 'semantic', label: 'Semantic', hint: 'embedding similarity only' },
  { id: 'keyword', label: 'Keyword', hint: 'BM25 exact-term matching' },
]

export default function Search() {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('hybrid')
  const [topK, setTopK] = useState(8)
  const [department, setDepartment] = useState('')
  const [category, setCategory] = useState('')
  const [results, setResults] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const run = async (e) => {
    e?.preventDefault()
    if (!query.trim()) return
    setBusy(true)
    setError(null)
    try {
      const filters = {}
      if (department.trim()) filters.department = department.trim()
      if (category.trim()) filters.category = category.trim()
      const data = await api.post('/search', {
        query: query.trim(),
        mode,
        top_k: topK,
        filters: Object.keys(filters).length ? filters : null,
      })
      setResults(data)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader title="Search" subtitle="Hybrid semantic + keyword retrieval across your indexed documents" />
      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      <form onSubmit={run} className="card mb-6 p-5">
        <div className="flex gap-3">
          <input
            className="input flex-1" placeholder="Search your knowledge base… e.g. lockout tagout requirements"
            value={query} onChange={(e) => setQuery(e.target.value)} autoFocus
          />
          <button className="btn-primary" disabled={busy || !query.trim()}>
            {busy ? <Spinner size="h-4 w-4" /> : '🔍 Search'}
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-4">
          <div className="flex rounded-lg border border-slate-700 bg-slate-950/60 p-0.5">
            {MODES.map((m) => (
              <button
                key={m.id} type="button" title={m.hint}
                onClick={() => setMode(m.id)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  mode === m.id ? 'bg-brand-600 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          <label className="flex items-center gap-2 text-xs text-slate-400">
            Top-K
            <input type="range" min="3" max="20" value={topK} onChange={(e) => setTopK(Number(e.target.value))}
                   className="accent-brand-500" />
            <span className="w-6 font-mono text-slate-300">{topK}</span>
          </label>

          <input className="input !w-44" placeholder="Department filter…" value={department}
                 onChange={(e) => setDepartment(e.target.value)} />
          <input className="input !w-40" placeholder="Category filter…" value={category}
                 onChange={(e) => setCategory(e.target.value)} />
        </div>
      </form>

      {results && (
        <div className="mb-4 flex items-center gap-3 text-xs text-slate-500">
          <span><b className="text-slate-300">{results.total}</b> results</span>
          <span>·</span>
          <span>{results.took_ms.toFixed(0)} ms</span>
          <span>·</span>
          <span>mode: <b className="text-slate-300">{results.mode}</b></span>
          <span>·</span>
          <span>embeddings: <b className="text-slate-300">{results.embedding_provider}</b></span>
        </div>
      )}

      {results && results.hits.length === 0 && (
        <EmptyState icon="🔍" title="No matches"
                    hint="Try different keywords, another retrieval mode, or upload documents covering this topic." />
      )}

      <div className="space-y-3">
        {results?.hits?.map((hit, i) => (
          <motion.div key={hit.chunk_id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.03 }} className="card p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-slate-100">{hit.document_title}</span>
                  <span className="badge bg-slate-800 text-slate-400">
                    {hit.page_start === hit.page_end ? `p.${hit.page_start}` : `pp.${hit.page_start}–${hit.page_end}`}
                  </span>
                  {hit.sources.map((s) => (
                    <span key={s} className={`badge ${s === 'vector' ? 'bg-violet-500/10 text-violet-400' : 'bg-sky-500/10 text-sky-400'}`}>
                      {s}
                    </span>
                  ))}
                  {hit.metadata?.department && (
                    <span className="badge bg-slate-800/80 text-slate-500">{hit.metadata.department}</span>
                  )}
                </div>
                <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-slate-400">{hit.snippet}</p>
                <div className="mt-1.5 text-[10px] text-slate-600">{hit.filename} · chunk #{hit.chunk_id}</div>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-lg font-bold text-brand-400">{(hit.score * 100).toFixed(0)}</div>
                <div className="text-[10px] uppercase tracking-wider text-slate-600">score</div>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
