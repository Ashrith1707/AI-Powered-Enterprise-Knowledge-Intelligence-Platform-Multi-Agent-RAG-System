import { motion } from 'framer-motion'
import {
  Database, FileText, HardDrive, Search as SearchIcon, Timer, UploadCloud,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState, ErrorState } from '@/components/shared/States'
import { StatusBadge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { StatCardSkeleton } from '@/components/ui/skeleton'
import { useDashboard } from '@/hooks/useAnalytics'
import { useDocuments } from '@/hooks/useDocuments'
import { formatBytes, formatRelative } from '@/utils/format'

const CHART = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)']

/* ---------- helpers over real API data ---------- */

function uploadTrend(docs, days = 14) {
  const buckets = new Map()
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000)
    buckets.set(d.toISOString().slice(0, 10), 0)
  }
  docs?.forEach((doc) => {
    const key = doc.uploaded_at?.slice(0, 10)
    if (buckets.has(key)) buckets.set(key, buckets.get(key) + 1)
  })
  return [...buckets].map(([date, count]) => ({
    label: new Date(date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    count,
  }))
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-edge bg-surface px-3 py-2 text-xs shadow-md">
      <p className="font-medium text-ink">{payload[0].payload.label ?? label}</p>
      <p className="mt-0.5 text-muted">{payload[0].name}: <span className="font-semibold text-ink">{payload[0].value}</span></p>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, sub, index }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.3 }}
    >
      <Card className="transition-shadow hover:shadow-md">
        <CardContent className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-muted">{label}</p>
            <p className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">{value}</p>
            {sub && <p className="mt-1 text-[11px] text-muted">{sub}</p>}
          </div>
          <div className="rounded-xl bg-primary-soft p-2.5">
            <Icon className="h-4.5 w-4.5 text-primary" />
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}

/* ---------- page ---------- */

export default function DashboardPage() {
  const { data: stats, isLoading, error, refetch } = useDashboard()
  const { data: docs } = useDocuments()

  if (error) return <ErrorState message={error.message} onRetry={refetch} />

  const storage = docs?.reduce((sum, d) => sum + (d.file_size ?? 0), 0) ?? 0
  const trend = uploadTrend(docs)
  const categories = Object.entries(stats?.documents_by_category ?? {})
    .map(([name, value]) => ({ label: name, value }))
    .sort((a, b) => b.value - a.value)
  const types = Object.entries(stats?.documents_by_type ?? {})
    .map(([name, value]) => ({ name, value }))
  const recentDocs = (docs ?? []).slice(0, 6)

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Live overview of your enterprise knowledge base."
        actions={
          <Link to="/upload">
            <Button><UploadCloud className="h-4 w-4" /> Upload document</Button>
          </Link>
        }
      />

      {/* Stat tiles */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)
        ) : (
          <>
            <StatCard index={0} icon={FileText} label="Total documents"
              value={stats.total_documents}
              sub={`${stats.indexed_documents} indexed · ${stats.failed_documents} failed`} />
            <StatCard index={1} icon={Database} label="Knowledge chunks"
              value={stats.total_chunks} sub={`${stats.total_pages} pages extracted`} />
            <StatCard index={2} icon={SearchIcon} label="Searches"
              value={stats.total_searches} sub="semantic + AI answers" />
            <StatCard index={3} icon={HardDrive} label="Storage used"
              value={formatBytes(storage)} sub={<span className="inline-flex items-center gap-1"><Timer className="h-3 w-3" />{stats.avg_latency_ms} ms avg latency</span>} />
          </>
        )}
      </div>

      {/* Charts row */}
      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Upload activity</CardTitle>
              <CardDescription>Documents added, last 14 days</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
                <defs>
                  <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} strokeDasharray="0" />
                <XAxis dataKey="label" tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tickLine={false} axisLine={false} allowDecimals={false} width={46} />
                <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'var(--chart-axis)', strokeWidth: 1 }} />
                <Area type="monotone" dataKey="count" name="Uploads"
                  stroke="var(--chart-1)" strokeWidth={2} fill="url(#trendFill)"
                  activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface)' }} />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Documents by category</CardTitle>
              <CardDescription>Auto-classified at ingestion</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="h-64">
            {categories.length === 0 ? (
              <EmptyState title="No documents yet" hint="Upload files to see categories." />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categories} layout="vertical" margin={{ top: 0, right: 28, left: -8, bottom: 0 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="label" tickLine={false} axisLine={false} width={78} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--surface-2)' }} />
                  <Bar dataKey="value" name="Documents" fill="var(--chart-1)"
                    radius={[0, 4, 4, 0]} barSize={14}
                    label={{ position: 'right', fill: 'var(--ink)', fontSize: 11 }} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Bottom row */}
      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>File types</CardTitle>
              <CardDescription>Distribution of sources</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            {types.length === 0 ? (
              <EmptyState title="Nothing indexed yet" />
            ) : (
              <>
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Tooltip content={<ChartTooltip />} />
                      <Pie data={types} dataKey="value" nameKey="name"
                        innerRadius={44} outerRadius={64} paddingAngle={2}
                        stroke="var(--surface)" strokeWidth={2}>
                        {types.map((_, i) => (
                          <Cell key={i} fill={CHART[i % CHART.length]} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-3 space-y-1.5">
                  {types.map((t, i) => (
                    <div key={t.name} className="flex items-center gap-2 text-xs">
                      <span className="h-2.5 w-2.5 rounded-sm" style={{ background: CHART[i % CHART.length] }} />
                      <span className="uppercase text-ink-2">{t.name}</span>
                      <span className="ml-auto font-semibold text-ink">{t.value}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Recent uploads</CardTitle>
              <CardDescription>Latest documents and their pipeline status</CardDescription>
            </div>
            <Link to="/documents" className="text-xs font-medium text-primary hover:underline">View all</Link>
          </CardHeader>
          <CardContent>
            {recentDocs.length === 0 ? (
              <EmptyState
                title="No uploads yet"
                hint="Your ingestion pipeline is idle. Upload a PDF, DOCX, TXT or scan to begin."
                action={<Link to="/upload"><Button size="sm">Upload now</Button></Link>}
              />
            ) : (
              <ul className="divide-y divide-edge">
                {recentDocs.map((d) => (
                  <li key={d.id} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                    <div className="rounded-lg bg-surface-2 p-2">
                      <FileText className="h-4 w-4 text-muted" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-ink">{d.filename}</p>
                      <p className="text-[11px] text-muted">
                        {d.category} · {d.page_count} pages · {formatBytes(d.file_size)} · {formatRelative(d.uploaded_at)}
                      </p>
                    </div>
                    <StatusBadge status={d.status} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
