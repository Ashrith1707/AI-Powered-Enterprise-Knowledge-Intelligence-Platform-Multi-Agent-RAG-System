import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../api/client'
import { EmptyState, ErrorBanner, PageHeader, Spinner, StatCard, StatusBadge } from '../components/ui'

const STATUS_COLORS = {
  completed: '#34d399', processing: '#38bdf8', pending: '#94a3b8', ocr: '#a78bfa', failed: '#f87171',
}

const fmtBytes = (n) => {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export default function Dashboard() {
  const [overview, setOverview] = useState(null)
  const [docs, setDocs] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      api.get('/analytics/overview'),
      api.get('/documents?page_size=6'),
    ])
      .then(([o, d]) => { if (alive) { setOverview(o); setDocs(d) } })
      .catch((e) => alive && setError(e))
    return () => { alive = false }
  }, [])

  if (error) return <ErrorBanner error={error} />
  if (!overview || !docs) {
    return <div className="flex justify-center py-24"><Spinner size="h-8 w-8" /></div>
  }

  const statusData = Object.entries(overview.documents_by_status || {}).map(([name, value]) => ({ name, value }))
  const uploadData = (overview.uploads_last_14_days || []).map((d) => ({
    day: d.date.slice(5), count: d.count,
  }))

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Your enterprise knowledge base at a glance"
        actions={
          <>
            <Link to="/documents" className="btn-secondary">＋ Upload documents</Link>
            <Link to="/ask" className="btn-primary">✦ Ask AI</Link>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label="Documents" value={overview.documents_total} icon="🗎"
                  sub={`${fmtBytes(overview.total_bytes)} ingested`} />
        <StatCard label="Indexed chunks" value={overview.total_chunks} icon="🧩" accent="text-emerald-400"
                  sub={`${(overview.total_chars || 0).toLocaleString()} characters`} />
        <StatCard label="Questions asked" value={overview.questions_asked} icon="✦" accent="text-violet-400"
                  sub={`${overview.conversations} conversations`} />
        <StatCard label="Answers generated" value={overview.answers_generated} icon="💬" accent="text-sky-400"
                  sub="grounded with citations" />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="card p-5 xl:col-span-2">
          <h3 className="mb-4 text-sm font-semibold text-slate-300">Uploads — last 14 days</h3>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={uploadData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 10 }} />
                <YAxis allowDecimals={false} tick={{ fill: '#64748b', fontSize: 10 }} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-5">
          <h3 className="mb-4 text-sm font-semibold text-slate-300">Processing status</h3>
          {statusData.length === 0 ? (
            <p className="py-10 text-center text-xs text-slate-500">No documents yet.</p>
          ) : (
            <>
              <div className="h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={statusData} dataKey="value" nameKey="name" innerRadius={42} outerRadius={65} paddingAngle={3}>
                      {statusData.map((entry) => (
                        <Cell key={entry.name} fill={STATUS_COLORS[entry.name] || '#64748b'} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-2 flex flex-wrap justify-center gap-3">
                {statusData.map((s) => (
                  <span key={s.name} className="flex items-center gap-1.5 text-[11px] text-slate-400">
                    <span className="h-2 w-2 rounded-full" style={{ background: STATUS_COLORS[s.name] || '#64748b' }} />
                    {s.name} · {s.value}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="card mt-6 overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
          <h3 className="text-sm font-semibold text-slate-300">Recent documents</h3>
          <Link to="/documents" className="text-xs font-medium text-brand-400 hover:text-brand-300">View all →</Link>
        </div>
        {docs.items.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No documents uploaded yet"
              hint="Upload PDFs, DOCX, text files or scans. KnowledgeIQ will OCR, parse, chunk, embed and index them for the AI agents."
              action={<Link to="/documents" className="btn-primary">Upload your first document</Link>}
            />
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-950/50 text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-5 py-2.5">Name</th>
                <th className="px-5 py-2.5">Type</th>
                <th className="px-5 py-2.5">Status</th>
                <th className="px-5 py-2.5">Pages</th>
                <th className="px-5 py-2.5">Chunks</th>
                <th className="px-5 py-2.5">Uploaded</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {docs.items.map((d) => (
                <tr key={d.id} className="transition hover:bg-slate-800/30">
                  <td className="max-w-[280px] truncate px-5 py-3 font-medium text-slate-200">{d.filename}</td>
                  <td className="px-5 py-3"><span className="badge bg-slate-800 uppercase text-slate-400">{d.file_type}</span></td>
                  <td className="px-5 py-3"><StatusBadge status={d.status} /></td>
                  <td className="px-5 py-3 text-slate-400">{d.page_count}</td>
                  <td className="px-5 py-3 text-slate-400">{d.chunk_count}</td>
                  <td className="px-5 py-3 text-xs text-slate-500">
                    {d.created_at ? new Date(d.created_at).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
