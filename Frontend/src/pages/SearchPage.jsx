import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowRight, Clock, Copy, FileSearch, FileText, Info, MessageSquareText, Search, SlidersHorizontal, X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { DocumentDrawer } from '@/components/documents/DocumentDrawer'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState } from '@/components/shared/States'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/toast'
import { useDashboard } from '@/hooks/useAnalytics'
import { useDebounce } from '@/hooks/useDebounce'
import { useDocuments } from '@/hooks/useDocuments'
import { useLocalStorage } from '@/hooks/useLocalStorage'
import { useSemanticSearch } from '@/hooks/useSearch'
import { cn } from '@/utils/cn'
import { highlightTerms } from '@/utils/highlight'

export default function SearchPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { push } = useToast()
  const { data: stats } = useDashboard()
  const { data: docs } = useDocuments()
  const search = useSemanticSearch()
  const [recent, setRecent] = useLocalStorage('eki.recentSearches', [])

  const [query, setQuery] = useState(params.get('q') ?? '')
  const [category, setCategory] = useState('all')
  const [threshold, setThreshold] = useState(0)
  const [showFilters, setShowFilters] = useState(false)
  const [drawerDoc, setDrawerDoc] = useState(null)

  const debounced = useDebounce(query, 400)

  // Instant search: fires automatically as you stop typing (real API call).
  useEffect(() => {
    const q = debounced.trim()
    if (q.length < 2) return
    search.mutate({ query: q, top_k: 20 })
    setRecent((prev) => [q, ...prev.filter((r) => r !== q)].slice(0, 8))
  }, [debounced]) // eslint-disable-line react-hooks/exhaustive-deps

  const categoryByDoc = useMemo(
    () => new Map((docs ?? []).map((d) => [d.id, d.category])),
    [docs],
  )
  const categories = useMemo(
    () => [...new Set((docs ?? []).map((d) => d.category))].sort(),
    [docs],
  )

  const result = search.data
  const hits = useMemo(() => {
    let list = result?.hits ?? []
    if (category !== 'all') list = list.filter((h) => categoryByDoc.get(h.document_id) === category)
    if (threshold > 0) list = list.filter((h) => h.score >= threshold)
    return list
  }, [result, category, threshold, categoryByDoc])

  const suggestions = (stats?.recent_queries ?? []).slice(0, 4)

  return (
    <div>
      <PageHeader
        title="Semantic Search"
        description="Meaning-based retrieval across every indexed chunk — not keyword matching."
      />

      {/* Search bar */}
      <div className="relative mx-auto max-w-2xl">
        <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" />
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Describe what you're looking for…"
          aria-label="Semantic search query"
          className="h-13 w-full rounded-2xl border border-edge bg-surface pl-12 pr-24 text-[15px] text-ink shadow-sm placeholder:text-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
        />
        <div className="absolute right-2.5 top-1/2 flex -translate-y-1/2 items-center gap-1">
          {query && (
            <button onClick={() => setQuery('')} aria-label="Clear search"
              className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink">
              <X className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={() => setShowFilters((s) => !s)}
            aria-label="Toggle filters" aria-expanded={showFilters}
            className={cn('rounded-lg p-1.5', showFilters ? 'bg-primary-soft text-primary' : 'text-muted hover:bg-surface-2')}
          >
            <SlidersHorizontal className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Filters */}
      <AnimatePresence>
        {showFilters && (
          <motion.div
            initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            className="mx-auto max-w-2xl overflow-hidden"
          >
            <div className="mt-3 flex flex-wrap items-center gap-4 rounded-xl border border-edge bg-surface p-3.5 text-xs">
              <label className="flex items-center gap-2 text-muted">
                Category
                <select value={category} onChange={(e) => setCategory(e.target.value)}
                  className="h-8 rounded-lg border border-edge bg-surface px-2 text-xs text-ink focus:border-primary focus:outline-none">
                  <option value="all">All</option>
                  {categories.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label className="flex flex-1 items-center gap-2 text-muted">
                Min similarity <span className="font-semibold tabular-nums text-ink">{threshold.toFixed(2)}</span>
                <input type="range" min="0" max="0.9" step="0.05" value={threshold}
                  onChange={(e) => setThreshold(parseFloat(e.target.value))}
                  className="flex-1 accent-[var(--primary)]" aria-label="Minimum similarity score" />
              </label>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Idle state: recent + suggested */}
      {!result && !search.isPending && (
        <div className="mx-auto mt-8 max-w-2xl space-y-6">
          {recent.length > 0 && (
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">Recent searches</p>
              <div className="flex flex-wrap gap-2">
                {recent.map((r) => (
                  <button key={r} onClick={() => setQuery(r)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-edge bg-surface px-3 py-1.5 text-xs text-ink-2 hover:border-primary hover:text-primary">
                    <Clock className="h-3 w-3" /> {r}
                  </button>
                ))}
              </div>
            </div>
          )}
          {suggestions.length > 0 && (
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
                Popular on this workspace
              </p>
              <div className="space-y-1.5">
                {suggestions.map((s, i) => (
                  <button key={i} onClick={() => setQuery(s)}
                    className="flex w-full items-center gap-2.5 rounded-xl border border-edge bg-surface px-4 py-2.5 text-left text-xs text-ink-2 hover:border-primary">
                    <Search className="h-3.5 w-3.5 shrink-0 text-muted" />
                    <span className="flex-1 truncate">{s}</span>
                    <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Loading */}
      {search.isPending && (
        <div className="mx-auto mt-6 max-w-2xl space-y-3">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-28 w-full rounded-xl" />)}
        </div>
      )}

      {/* Results */}
      {result && !search.isPending && (
        <div className="mx-auto mt-6 max-w-2xl">
          <p className="mb-3 flex items-center gap-1.5 text-xs text-muted">
            <Info className="h-3.5 w-3.5" />
            {hits.length} of {result.hits.length} chunks shown · {result.latency_ms} ms
          </p>
          {hits.length === 0 ? (
            <Card>
              <EmptyState icon={FileSearch} title="No matching chunks"
                hint={result.hits.length > 0
                  ? 'Your filters removed all results — lower the similarity threshold.'
                  : 'Try rephrasing, or upload more documents to grow the knowledge base.'} />
            </Card>
          ) : (
            <div className="space-y-3">
              <AnimatePresence initial={false}>
                {hits.map((hit, i) => (
                  <motion.div
                    key={hit.chunk_id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: Math.min(i * 0.04, 0.3) }}
                  >
                    <Card className="group p-4 transition-all hover:border-primary/40 hover:shadow-md">
                      <div className="mb-2 flex items-center gap-2">
                        <FileText className="h-4 w-4 shrink-0 text-primary" />
                        <button onClick={() => setDrawerDoc(hit.document_id)}
                          className="min-w-0 flex-1 truncate text-left text-sm font-medium text-ink hover:text-primary">
                          {hit.document_name}
                        </button>
                        <Badge tone="blue">{categoryByDoc.get(hit.document_id) ?? '…'}</Badge>
                        <span className="rounded-full bg-primary-soft px-2 py-0.5 text-[10px] font-semibold tabular-nums text-primary"
                          title="Cosine similarity">
                          {hit.score.toFixed(3)}
                        </span>
                      </div>
                      <p className="text-xs leading-relaxed text-ink-2">
                        {highlightTerms(hit.snippet, debounced)}…
                      </p>
                      <div className="mt-2.5 flex items-center gap-1 text-[10px] text-muted">
                        page {hit.page_number} · chunk #{hit.chunk_id}
                        <span className="ml-auto flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                          <Button size="sm" variant="ghost" onClick={() => setDrawerDoc(hit.document_id)}>
                            <FileText className="h-3 w-3" /> Open
                          </Button>
                          <Button size="sm" variant="ghost"
                            onClick={() => navigate(`/ask?q=${encodeURIComponent(debounced)}`)}>
                            <MessageSquareText className="h-3 w-3" /> Ask AI
                          </Button>
                          <Button size="sm" variant="ghost" aria-label="Copy document ID"
                            onClick={() => { navigator.clipboard.writeText(String(hit.document_id)); push('Document ID copied', 'success') }}>
                            <Copy className="h-3 w-3" />
                          </Button>
                        </span>
                      </div>
                    </Card>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>
      )}

      <DocumentDrawer documentId={drawerDoc} highlight={debounced} onClose={() => setDrawerDoc(null)} />
    </div>
  )
}
