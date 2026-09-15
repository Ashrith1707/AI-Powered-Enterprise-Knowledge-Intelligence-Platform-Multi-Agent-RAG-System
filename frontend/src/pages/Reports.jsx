import { useEffect, useState } from 'react'
import { api, tokenStore } from '../api/client'
import { ErrorBanner, PageHeader, Spinner } from '../components/ui'

function Section({ title, children }) {
  return (
    <div className="card p-5">
      <h3 className="mb-4 text-sm font-semibold text-slate-300">{title}</h3>
      {children}
    </div>
  )
}

function KV({ k, v }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-800/60 py-1.5 text-xs last:border-0">
      <span className="text-slate-500">{k}</span>
      <span className="font-medium text-slate-200">{v ?? '—'}</span>
    </div>
  )
}

function BarRow({ label, value, max }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div className="py-1">
      <div className="flex justify-between text-xs">
        <span className="text-slate-400">{label}</span>
        <span className="font-mono text-slate-300">{value}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-800">
        <div className="h-full rounded-full bg-brand-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function Reports() {
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/reports/summary').then(setReport).catch(setError)
  }, [])

  const exportCsv = () => {
    // Direct download with the bearer token
    fetch('/api/reports/export', { headers: { Authorization: `Bearer ${tokenStore.access}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'knowledgeiq-documents.csv'
        a.click()
        URL.revokeObjectURL(url)
      })
      .catch(setError)
  }

  if (error) return <ErrorBanner error={error} />
  if (!report) return <div className="flex justify-center py-24"><Spinner size="h-8 w-8" /></div>

  const maxDept = Math.max(1, ...Object.values(report.documents.by_department || {}))
  const maxCat = Math.max(1, ...Object.values(report.documents.by_category || {}))

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle={`Generated ${new Date(report.generated_at).toLocaleString()}`}
        actions={<button onClick={exportCsv} className="btn-secondary">⬇ Export CSV</button>}
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Section title="📄 Document inventory">
          <KV k="Total documents" v={report.documents.total} />
          <KV k="Total chunks" v={report.documents.total_chunks} />
          <KV k="Total characters" v={(report.documents.total_chars || 0).toLocaleString()} />
          <div className="mt-3">
            {Object.entries(report.documents.by_status || {}).map(([s, c]) => (
              <KV key={s} k={s} v={c} />
            ))}
          </div>
        </Section>

        <Section title="🏢 By department">
          {Object.entries(report.documents.by_department || {}).map(([d, c]) => (
            <BarRow key={d} label={d} value={c} max={maxDept} />
          ))}
          <div className="mt-4 border-t border-slate-800 pt-3">
            <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-slate-500">By category</div>
            {Object.entries(report.documents.by_category || {}).map(([d, c]) => (
              <BarRow key={d} label={d} value={c} max={maxCat} />
            ))}
          </div>
        </Section>

        <Section title="✦ AI usage">
          <KV k="Conversations" v={report.usage.conversations} />
          <KV k="Questions asked" v={report.usage.questions_asked} />
          <KV k="Answers generated" v={report.usage.answers_generated} />
          <KV k="Passed verification" v={report.usage.answers_passing_verification} />
          <KV k="Verification rate" v={report.usage.verification_rate != null ? `${(report.usage.verification_rate * 100).toFixed(1)}%` : '—'} />
          <div className="mt-3 rounded-lg bg-slate-950/60 p-3">
            <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">AI providers</div>
            <KV k="LLM" v={report.system.llm_provider} />
            <KV k="Embeddings" v={`${report.system.embeddings.provider} (${report.system.embeddings.dimensions}d)`} />
            <KV k="Vector store" v={`${report.system.vector_store.backend} · ${report.system.vector_store.vector_count} vectors`} />
          </div>
        </Section>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Section title="📎 Top cited documents">
          {report.top_cited_documents.length === 0 ? (
            <p className="py-4 text-center text-xs text-slate-600">No citations yet.</p>
          ) : (
            report.top_cited_documents.map((d) => (
              <KV key={d.document_id} k={d.filename} v={`${d.citations} citation(s)`} />
            ))
          )}
        </Section>

        <Section title="🕒 Recent documents">
          {report.recent_documents.map((d) => (
            <KV key={d.id} k={`${d.filename} (${d.status})`} v={`${d.pages}p · ${d.chunks} chunks`} />
          ))}
        </Section>
      </div>
    </div>
  )
}
