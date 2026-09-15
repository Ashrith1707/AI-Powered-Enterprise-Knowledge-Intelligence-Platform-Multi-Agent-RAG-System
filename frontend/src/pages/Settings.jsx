import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { ErrorBanner, PageHeader, Spinner } from '../components/ui'
import { useAuth } from '../context/AuthContext'

function Row({ k, v, tone = 'text-slate-200' }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-800/60 py-2 text-xs last:border-0">
      <span className="text-slate-500">{k}</span>
      <span className={`font-mono ${tone}`}>{v}</span>
    </div>
  )
}

export default function Settings() {
  const { user } = useAuth()
  const [health, setHealth] = useState(null)
  const [evalResults, setEvalResults] = useState(null)
  const [runState, setRunState] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/health').then(setHealth).catch(setError)
    api.get('/evaluation/results?limit=5').then((r) => setEvalResults(r.items)).catch(() => {})
  }, [])

  const triggerEval = async () => {
    setRunState('starting')
    try {
      await api.post('/evaluation/run', {})
      setRunState('running')
      const poll = setInterval(async () => {
        try {
          const r = await api.get('/evaluation/results?limit=5')
          if (r.items.length > (evalResults?.length || 0)) {
            setEvalResults(r.items)
            setRunState('done')
            clearInterval(poll)
            setTimeout(() => setRunState(null), 4000)
          }
        } catch { /* keep polling */ }
      }, 3000)
      setTimeout(() => { clearInterval(poll); setRunState((s) => (s === 'running' ? 'timeout' : s)) }, 120000)
    } catch (e) {
      setError(e)
      setRunState(null)
    }
  }

  if (error && !health) return <ErrorBanner error={error} />

  return (
    <div>
      <PageHeader title="Settings" subtitle="System configuration and AI provider status" />
      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      {!health ? (
        <div className="flex justify-center py-16"><Spinner size="h-8 w-8" /></div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div className="card p-5">
            <h3 className="mb-3 text-sm font-semibold text-slate-300">🧠 AI providers</h3>
            <Row k="LLM provider" v={health.llm.provider}
                 tone={health.llm.provider === 'gemini' ? 'text-emerald-400' : 'text-amber-400'} />
            <Row k="Generation model" v={health.llm.model} />
            <Row k="Embedding provider" v={health.embeddings.provider}
                 tone={health.embeddings.provider === 'gemini' ? 'text-emerald-400' : 'text-amber-400'} />
            <Row k="Embedding model" v={health.embeddings.model} />
            <Row k="Embedding dimensions" v={health.embeddings.dimensions} />
            {health.embeddings.probe_error && (
              <div className="mt-2 rounded-lg border border-amber-800/50 bg-amber-950/30 p-2 text-[11px] text-amber-300">
                Gemini embedding probe failed: {health.embeddings.probe_error}
              </div>
            )}
            {health.llm.provider === 'mock' && (
              <div className="mt-3 rounded-lg border border-amber-800/50 bg-amber-950/30 p-3 text-[11px] leading-relaxed text-amber-300">
                <b>Offline mock mode.</b> Answers are extractive (quoted directly from evidence) and embeddings are
                lexical hashes. Set <code className="rounded bg-black/40 px-1 font-mono">GEMINI_API_KEY</code> in
                <code className="rounded bg-black/40 px-1 font-mono">backend/.env</code> and restart the API for full
                generative answers and semantic embeddings (<code className="font-mono">gemini-embedding-001</code> —
                the deprecated <code className="font-mono">text-embedding-004</code> is never used).
              </div>
            )}
          </div>

          <div className="card p-5">
            <h3 className="mb-3 text-sm font-semibold text-slate-300">🗄 Storage & OCR</h3>
            <Row k="Database" v={health.database} tone={health.database === 'ok' ? 'text-emerald-400' : 'text-red-400'} />
            <Row k="Vector store" v={`${health.vector_store.backend} (${health.vector_store.vector_count} vectors)`} />
            <Row k="FAISS available" v={String(health.faiss_available)} />
            <Row k="Tesseract OCR" v={health.ocr.tesseract ? 'available' : 'not installed'}
                 tone={health.ocr.tesseract ? 'text-emerald-400' : 'text-amber-400'} />
            <Row k="Scanned-PDF rendering" v={health.ocr.pdf_rendering ? 'available' : 'not installed'}
                 tone={health.ocr.pdf_rendering ? 'text-emerald-400' : 'text-amber-400'} />
            <Row k="Environment" v={health.env} />
            {health.config_problems?.length > 0 && (
              <div className="mt-3 space-y-1">
                {health.config_problems.map((p) => (
                  <div key={p} className="rounded bg-red-950/40 px-2 py-1 text-[11px] text-red-300">⚠ {p}</div>
                ))}
              </div>
            )}
          </div>

          <div className="card p-5 xl:col-span-2">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-300">🎯 RAG evaluation</h3>
              {user?.role === 'admin' && (
                <button onClick={triggerEval} disabled={runState === 'starting' || runState === 'running'}
                        className="btn-secondary !py-1.5 !text-xs">
                  {runState === 'running' ? 'Running evaluation…' : runState === 'done' ? '✓ New results loaded' : '▶ Run golden-dataset evaluation'}
                </button>
              )}
            </div>
            <p className="mb-3 text-[11px] leading-relaxed text-slate-500">
              Runs the labeled golden dataset (data/evaluation/golden_dataset.json) through the full agent pipeline and
              computes Precision@K / Recall@K / MRR / nDCG plus faithfulness, citation accuracy and groundedness.
              CLI equivalent: <code className="rounded bg-slate-950 px-1 font-mono text-slate-400">python -m app.evaluation.run</code>
            </p>
            {evalResults && evalResults.length > 0 ? (
              <table className="w-full text-left text-xs">
                <thead className="text-[10px] uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="py-2">Run</th><th>Queries</th><th>Recall@5</th><th>MRR</th>
                    <th>nDCG@5</th><th>Faithfulness</th><th>Citation acc.</th><th>Overall</th><th>When</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {evalResults.map((r) => (
                    <tr key={r.run_id}>
                      <td className="py-2 font-mono text-[10px] text-slate-400">{r.run_id.slice(5, 24)}</td>
                      <td>{r.num_queries}</td>
                      <td className="font-mono">{r.retrieval_metrics?.['recall@5'] ?? '—'}</td>
                      <td className="font-mono">{r.retrieval_metrics?.mrr ?? '—'}</td>
                      <td className="font-mono">{r.retrieval_metrics?.['ndcg@5'] ?? '—'}</td>
                      <td className="font-mono">{r.generation_metrics?.faithfulness ?? '—'}</td>
                      <td className="font-mono">{r.generation_metrics?.citation_accuracy ?? '—'}</td>
                      <td className="font-mono font-bold text-brand-400">{r.overall_score ?? '—'}</td>
                      <td className="text-slate-500">{r.created_at ? new Date(r.created_at).toLocaleString() : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="py-4 text-center text-xs text-slate-600">
                No evaluation runs yet. {user?.role === 'admin' ? 'Click the button above to run one.' : 'Admins can trigger runs.'}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
