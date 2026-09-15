import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../api/client'
import { ErrorBanner, PageHeader, Spinner, StatCard } from '../components/ui'

const TOOLTIP_STYLE = { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }

export default function Analytics() {
  const [overview, setOverview] = useState(null)
  const [perf, setPerf] = useState(null)
  const [topDocs, setTopDocs] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([
      api.get('/analytics/overview'),
      api.get('/analytics/performance'),
      api.get('/analytics/top-documents'),
    ])
      .then(([o, p, t]) => { setOverview(o); setPerf(p); setTopDocs(t) })
      .catch(setError)
  }, [])

  if (error) return <ErrorBanner error={error} />
  if (!overview || !perf) return <div className="flex justify-center py-24"><Spinner size="h-8 w-8" /></div>

  const uploads = (overview.uploads_last_14_days || []).map((d) => ({ day: d.date.slice(5), uploads: d.count }))
  const latencyBars = [
    { stage: 'retrieval', ms: perf.avg_retrieval_latency_ms || 0 },
    { stage: 'generation', ms: perf.avg_generation_latency_ms || 0 },
    { stage: 'verification', ms: perf.avg_verification_latency_ms || 0 },
    { stage: 'total', ms: perf.avg_total_latency_ms || 0 },
  ]

  return (
    <div>
      <PageHeader title="Analytics" subtitle="Pipeline performance and knowledge base activity — measured, not estimated" />

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label="Questions asked" value={overview.questions_asked} icon="✦" />
        <StatCard label="Avg pipeline latency" value={perf.avg_total_latency_ms != null ? `${perf.avg_total_latency_ms.toFixed(0)}ms` : '—'}
                  icon="⏱" accent="text-sky-400" sub={perf.p95_total_latency_ms != null ? `p95: ${perf.p95_total_latency_ms.toFixed(0)}ms` : undefined} />
        <StatCard label="Avg chunks retrieved" value={perf.avg_chunks_retrieved ?? '—'} icon="🧩" accent="text-violet-400"
                  sub={`${perf.sample_size} answers sampled`} />
        <StatCard label="Verification failures" value={perf.sample_size ? perf.sample_size - perf.answers_without_verification_failure : 0}
                  icon="🛡" accent="text-emerald-400" sub={`${perf.total_regenerations} regeneration(s)`} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card p-5">
          <h3 className="mb-4 text-sm font-semibold text-slate-300">Upload activity (14 days)</h3>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={uploads}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 10 }} />
                <YAxis allowDecimals={false} tick={{ fill: '#64748b', fontSize: 10 }} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Line type="monotone" dataKey="uploads" stroke="#818cf8" strokeWidth={2} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-5">
          <h3 className="mb-4 text-sm font-semibold text-slate-300">Average latency by stage (ms)</h3>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={latencyBars}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="stage" tick={{ fill: '#64748b', fontSize: 10 }} />
                <YAxis tick={{ fill: '#64748b', fontSize: 10 }} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="ms" fill="#38bdf8" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card p-5">
          <h3 className="mb-4 text-sm font-semibold text-slate-300">Most cited documents</h3>
          {topDocs?.items?.length ? (
            <div className="space-y-2">
              {topDocs.items.map((d) => (
                <div key={d.document_id} className="flex items-center justify-between rounded-lg bg-slate-950/60 px-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate text-xs font-medium text-slate-200">{d.title}</div>
                    <div className="text-[10px] text-slate-600">{d.filename}</div>
                  </div>
                  <span className="badge shrink-0 bg-brand-600/15 text-brand-300">📎 {d.citations}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-8 text-center text-xs text-slate-600">No citations recorded yet — ask some questions first.</p>
          )}
        </div>

        <div className="card p-5">
          <h3 className="mb-4 text-sm font-semibold text-slate-300">Provider usage (last {perf.sample_size} answers)</h3>
          {Object.keys(perf.provider_usage || {}).length ? (
            <div className="space-y-2">
              {Object.entries(perf.provider_usage).map(([provider, count]) => (
                <div key={provider} className="rounded-lg bg-slate-950/60 px-3 py-2">
                  <div className="flex justify-between text-xs">
                    <span className="font-mono text-slate-300">{provider}</span>
                    <span className="text-slate-500">{count}</span>
                  </div>
                  <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-slate-800">
                    <div className="h-full rounded-full bg-brand-500"
                         style={{ width: `${(count / perf.sample_size) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-8 text-center text-xs text-slate-600">No answers generated yet.</p>
          )}
        </div>
      </div>
    </div>
  )
}
