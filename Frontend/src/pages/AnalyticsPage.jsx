import { motion } from 'framer-motion'
import { Bot, Cpu, Gauge, Info, ScanText, Timer } from 'lucide-react'
import { useMemo } from 'react'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { PageHeader } from '@/components/shared/PageHeader'
import { ErrorState } from '@/components/shared/States'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { StatCardSkeleton, Skeleton } from '@/components/ui/skeleton'
import { useAgents, useDashboard, useSearchAnalytics } from '@/hooks/useAnalytics'
import { useDocuments } from '@/hooks/useDocuments'
import { formatBytes } from '@/utils/format'

const CHART = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)']

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const p = payload[0]
  return (
    <div className="rounded-lg border border-edge bg-surface px-3 py-2 text-xs shadow-md">
      <p className="font-medium text-ink">{p.payload.label ?? p.payload.name}</p>
      <p className="mt-0.5 text-muted">
        {p.name}: <span className="font-semibold text-ink">{p.payload.display ?? p.value}</span>
      </p>
    </div>
  )
}

function Tile({ icon: Icon, label, value, sub, i }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
      <Card>
        <CardContent className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-muted">{label}</p>
            <p className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">{value}</p>
            {sub && <p className="mt-1 text-[11px] text-muted">{sub}</p>}
          </div>
          <div className="rounded-xl bg-primary-soft p-2.5"><Icon className="h-4.5 w-4.5 text-primary" /></div>
        </CardContent>
      </Card>
    </motion.div>
  )
}

export default function AnalyticsPage() {
  const { data: stats, isLoading, error, refetch } = useDashboard()
  const { data: docs } = useDocuments()
  const { data: agents } = useAgents()
  const { data: searchStats } = useSearchAnalytics(30)

  const derived = useMemo(() => {
    const list = docs ?? []
    // 30-day upload trend from real uploaded_at timestamps.
    const buckets = new Map()
    for (let i = 29; i >= 0; i--) {
      const d = new Date(Date.now() - i * 86400000)
      buckets.set(d.toISOString().slice(0, 10), 0)
    }
    list.forEach((d) => {
      const key = d.uploaded_at?.slice(0, 10)
      if (buckets.has(key)) buckets.set(key, buckets.get(key) + 1)
    })
    const trend = [...buckets].map(([date, count]) => ({
      label: new Date(date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
      count,
    }))

    // Processing duration = processed_at − uploaded_at (both real columns).
    const processed = list.filter((d) => d.processed_at && d.uploaded_at)
    const avgProcessMs = processed.length
      ? processed.reduce((s, d) => s + (new Date(d.processed_at) - new Date(d.uploaded_at)), 0) / processed.length
      : 0

    const ocrDocs = list.filter((d) => d.used_ocr).length

    const storageByCategory = Object.entries(
      list.reduce((acc, d) => {
        acc[d.category] = (acc[d.category] ?? 0) + d.file_size
        return acc
      }, {}),
    ).map(([name, bytes]) => ({ name, value: bytes, display: formatBytes(bytes) }))

    return { trend, avgProcessMs, ocrDocs, storageByCategory, totalDocs: list.length }
  }, [docs])

  if (error) return <ErrorState message={error.message} onRetry={refetch} />

  const categories = Object.entries(stats?.documents_by_category ?? {})
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value)

  return (
    <div>
      <PageHeader title="Analytics" description="Pipeline, retrieval and storage intelligence — computed from live platform data." />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)
        ) : (
          <>
            <Tile i={0} icon={Timer} label="Avg processing time"
              value={derived.avgProcessMs < 1000
                ? `${Math.round(derived.avgProcessMs)} ms`
                : `${(derived.avgProcessMs / 1000).toFixed(1)} s`}
              sub="upload → indexed, per document" />
            <Tile i={1} icon={ScanText} label="OCR usage"
              value={derived.totalDocs ? `${Math.round((derived.ocrDocs / derived.totalDocs) * 100)}%` : '0%'}
              sub={`${derived.ocrDocs} of ${derived.totalDocs} documents needed OCR`} />
            <Tile i={2} icon={Gauge} label="Avg search latency"
              value={`${stats.avg_latency_ms} ms`} sub={`${stats.total_searches} total searches`} />
            <Tile i={3} icon={Cpu} label="Embedding coverage"
              value={stats.total_chunks} sub={`chunks indexed from ${stats.total_pages} pages`} />
          </>
        )}
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Document growth</CardTitle>
              <CardDescription>Uploads per day, last 30 days</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="h-64">
            {!docs ? <Skeleton className="h-full" /> : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={derived.trend} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
                  <defs>
                    <linearGradient id="growthFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} interval={6} />
                  <YAxis tickLine={false} axisLine={false} allowDecimals={false} width={46} />
                  <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'var(--chart-axis)', strokeWidth: 1 }} />
                  <Area type="monotone" dataKey="count" name="Uploads" stroke="var(--chart-1)"
                    strokeWidth={2} fill="url(#growthFill)"
                    activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface)' }} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Storage by category</CardTitle>
              <CardDescription>{formatBytes((docs ?? []).reduce((s, d) => s + d.file_size, 0))} total</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            {derived.storageByCategory.length === 0 ? (
              <p className="py-8 text-center text-xs text-muted">No documents yet.</p>
            ) : (
              <>
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Tooltip content={<ChartTooltip />} />
                      <Pie data={derived.storageByCategory} dataKey="value" nameKey="name"
                        innerRadius={44} outerRadius={64} paddingAngle={2}
                        stroke="var(--surface)" strokeWidth={2}>
                        {derived.storageByCategory.map((_, i) => (
                          <Cell key={i} fill={CHART[i % CHART.length]} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-3 space-y-1.5">
                  {derived.storageByCategory.map((s, i) => (
                    <div key={s.name} className="flex items-center gap-2 text-xs">
                      <span className="h-2.5 w-2.5 rounded-sm" style={{ background: CHART[i % CHART.length] }} />
                      <span className="text-ink-2">{s.name}</span>
                      <span className="ml-auto font-semibold tabular-nums text-ink">{s.display}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Categories</CardTitle>
              <CardDescription>Documents per auto-classified category</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="h-56">
            {categories.length === 0 ? (
              <p className="py-8 text-center text-xs text-muted">No documents yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categories} layout="vertical" margin={{ top: 0, right: 28, left: -8, bottom: 0 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="label" tickLine={false} axisLine={false} width={78} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--surface-2)' }} />
                  <Bar dataKey="value" name="Documents" fill="var(--chart-1)" radius={[0, 4, 4, 0]}
                    barSize={14} label={{ position: 'right', fill: 'var(--ink)', fontSize: 11 }} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Agent registry</CardTitle>
              <CardDescription>Live from the coordinator — the workers behind every answer</CardDescription>
            </div>
            <Bot className="h-4 w-4 text-muted" />
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-xs">
              <thead>
                <tr className="border-b border-edge text-left text-muted">
                  <th className="py-2 pr-4 font-medium">Agent</th>
                  <th className="py-2 pr-4 font-medium">Responsibility</th>
                  <th className="py-2 font-medium">Capabilities</th>
                </tr>
              </thead>
              <tbody>
                {(agents ?? []).map((a) => (
                  <tr key={a.name} className="border-b border-edge last:border-0">
                    <td className="py-2.5 pr-4 font-mono font-medium text-ink">{a.name}</td>
                    <td className="py-2.5 pr-4 text-ink-2">{a.description}</td>
                    <td className="py-2.5">
                      <span className="flex flex-wrap gap-1">
                        {a.capabilities.map((c) => <Badge key={c}>{c}</Badge>)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>

      {/* Search trends — live from /api/analytics/searches */}
      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Search volume</CardTitle>
              <CardDescription>
                Queries per day, last 30 days · {searchStats?.total ?? 0} total
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="h-56">
            {!searchStats ? <Skeleton className="h-full" /> : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={searchStats.daily.map((d) => ({
                  label: new Date(d.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
                  value: d.count,
                }))} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} interval={6} />
                  <YAxis tickLine={false} axisLine={false} allowDecimals={false} width={46} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--surface-2)' }} />
                  <Bar dataKey="value" name="Searches" fill="var(--chart-2)" radius={[4, 4, 0, 0]} barSize={10} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Top queries</CardTitle>
              <CardDescription>Most frequent, last 30 days</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            {!searchStats?.top_queries?.length ? (
              <p className="py-8 text-center text-xs text-muted">No searches logged yet.</p>
            ) : (
              <ul className="space-y-2">
                {searchStats.top_queries.map((q, i) => (
                  <li key={i} className="flex items-center gap-2 text-xs">
                    <span className="w-4 shrink-0 font-semibold tabular-nums text-muted">{i + 1}.</span>
                    <span className="min-w-0 flex-1 truncate text-ink">{q.query}</span>
                    <span className="shrink-0 rounded-full bg-surface-2 px-2 py-0.5 font-semibold tabular-nums text-ink-2">
                      {q.count}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <p className="mt-5 flex items-start gap-1.5 text-[11px] text-muted">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        Per-user attribution charts arrive once search logs record user ids across sessions —
        the schema already has the column.
      </p>
    </div>
  )
}
