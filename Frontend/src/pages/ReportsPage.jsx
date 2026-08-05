import { zodResolver } from '@hookform/resolvers/zod'
import { motion } from 'framer-motion'
import {
  CalendarClock, Download, Eye, FileSpreadsheet, FileText, Plus, Sparkles,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { reportApi } from '@/api/report.api'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState, ErrorState } from '@/components/shared/States'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog } from '@/components/ui/dialog'
import { FieldError, Input, Label } from '@/components/ui/input'
import { TableSkeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/toast'
import { useCreateReport, useReports } from '@/hooks/useReports'
import { useDocuments } from '@/hooks/useDocuments'
import { cn } from '@/utils/cn'
import { formatDate } from '@/utils/format'

const schema = z.object({
  title: z.string().min(3, 'At least 3 characters').max(300),
  report_type: z.enum(['analytics', 'summary', 'qa']),
  file_format: z.enum(['pdf', 'docx']),
  document_ids: z.array(z.number()).default([]),
  question: z.string().optional(),
}).refine((d) => d.report_type !== 'qa' || (d.question && d.question.trim().length >= 3), {
  message: 'A question is required for Q&A reports',
  path: ['question'],
}).refine((d) => d.report_type !== 'summary' || d.document_ids.length > 0, {
  message: 'Select at least one document',
  path: ['document_ids'],
})

const TYPE_META = {
  analytics: { label: 'Analytics snapshot', desc: 'Platform metrics: documents, chunks, search activity' },
  summary: { label: 'Document summary', desc: 'Metadata + summaries for selected documents' },
  qa: { label: 'Q&A (RAG answer)', desc: 'An AI answer with citations, archived as a document' },
}

export default function ReportsPage() {
  const { data: reports, isLoading, error, refetch } = useReports()
  const { data: docs } = useDocuments()
  const createReport = useCreateReport()
  const { push } = useToast()
  const [typeFilter, setTypeFilter] = useState('all')
  const [preview, setPreview] = useState(null)

  const { register, handleSubmit, watch, setValue, reset, formState: { errors } } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { title: 'Platform Analytics Report', report_type: 'analytics', file_format: 'pdf', document_ids: [] },
  })
  const reportType = watch('report_type')
  const selectedIds = watch('document_ids')

  const onSubmit = async (values) => {
    try {
      const created = await createReport.mutateAsync({
        ...values,
        question: values.report_type === 'qa' ? values.question : null,
      })
      push(`Report #${created.id} generated`, 'success')
      reset({ ...values, title: values.title })
    } catch (err) {
      push(err.message, 'error')
    }
  }

  const filtered = useMemo(() => {
    const list = reports ?? []
    return typeFilter === 'all' ? list : list.filter((r) => r.report_type === typeFilter)
  }, [reports, typeFilter])

  if (error) return <ErrorState message={error.message} onRetry={refetch} />

  return (
    <div>
      <PageHeader title="Reports" description="Generate branded PDF and DOCX intelligence reports from live platform data." />

      <div className="grid gap-4 lg:grid-cols-5">
        {/* Generator */}
        <Card className="h-fit lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>New report</CardTitle>
              <CardDescription>Rendered server-side by ReportLab / python-docx</CardDescription>
            </div>
            <Sparkles className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
              <div>
                <Label htmlFor="rt">Title</Label>
                <Input id="rt" {...register('title')} />
                <FieldError>{errors.title?.message}</FieldError>
              </div>

              <div>
                <Label>Type</Label>
                <div className="space-y-1.5">
                  {Object.entries(TYPE_META).map(([value, meta]) => (
                    <label key={value} className={cn(
                      'flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 transition-colors',
                      reportType === value ? 'border-primary bg-primary-soft' : 'border-edge hover:border-primary/40',
                    )}>
                      <input type="radio" value={value} {...register('report_type')} className="mt-0.5 accent-[var(--primary)]" />
                      <span>
                        <span className="block text-xs font-medium text-ink">{meta.label}</span>
                        <span className="block text-[11px] text-muted">{meta.desc}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              {reportType === 'summary' && (
                <div>
                  <Label>Documents ({selectedIds.length} selected)</Label>
                  <div className="max-h-36 space-y-1 overflow-y-auto rounded-xl border border-edge p-2">
                    {(docs ?? []).map((d) => (
                      <label key={d.id} className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-ink-2 hover:bg-surface-2">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(d.id)}
                          onChange={(e) =>
                            setValue('document_ids', e.target.checked
                              ? [...selectedIds, d.id]
                              : selectedIds.filter((x) => x !== d.id),
                            { shouldValidate: true })}
                          className="accent-[var(--primary)]"
                        />
                        <span className="truncate">{d.filename}</span>
                      </label>
                    ))}
                    {(docs ?? []).length === 0 && <p className="p-2 text-xs text-muted">No documents uploaded yet.</p>}
                  </div>
                  <FieldError>{errors.document_ids?.message}</FieldError>
                </div>
              )}

              {reportType === 'qa' && (
                <div>
                  <Label htmlFor="rq">Question</Label>
                  <Input id="rq" placeholder="What should the AI answer and archive?" {...register('question')} />
                  <FieldError>{errors.question?.message}</FieldError>
                </div>
              )}

              <div>
                <Label>Format</Label>
                <div className="flex gap-2">
                  {['pdf', 'docx'].map((f) => (
                    <label key={f} className={cn(
                      'flex-1 cursor-pointer rounded-xl border py-2 text-center text-xs font-semibold uppercase transition-colors',
                      watch('file_format') === f ? 'border-primary bg-primary-soft text-primary' : 'border-edge text-muted hover:border-primary/40',
                    )}>
                      <input type="radio" value={f} {...register('file_format')} className="sr-only" />
                      {f}
                    </label>
                  ))}
                  {/* TODO(backend): CSV/XLSX export endpoints don't exist yet */}
                  <button type="button" title="Requires a backend CSV/Excel export endpoint — see TODO.md"
                    onClick={() => push('CSV/Excel export needs a backend endpoint (see TODO.md)', 'warning')}
                    className="flex-1 cursor-not-allowed rounded-xl border border-dashed border-edge py-2 text-center text-xs font-semibold uppercase text-muted opacity-60">
                    <FileSpreadsheet className="mx-auto mb-0.5 h-3.5 w-3.5" /> CSV
                  </button>
                </div>
              </div>

              <Button type="submit" className="w-full" loading={createReport.isPending}>
                <Plus className="h-4 w-4" /> Generate report
              </Button>
            </form>

            {/* Scheduled reports — honest placeholder */}
            <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-dashed border-edge p-3 opacity-70">
              <CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
              <p className="text-[11px] leading-relaxed text-muted">
                <span className="font-medium text-ink-2">Scheduled reports</span> — planned feature.
                Requires a backend scheduler endpoint (documented in TODO.md); nothing is simulated.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* History */}
        <Card className="lg:col-span-3">
          <CardHeader>
            <div>
              <CardTitle>History</CardTitle>
              <CardDescription>{filtered.length} report{filtered.length !== 1 && 's'}</CardDescription>
            </div>
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
              aria-label="Filter reports by type"
              className="h-8 rounded-lg border border-edge bg-surface px-2 text-xs text-ink-2 focus:border-primary focus:outline-none">
              <option value="all">All types</option>
              <option value="analytics">Analytics</option>
              <option value="summary">Summary</option>
              <option value="qa">Q&A</option>
            </select>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <TableSkeleton rows={5} />
            ) : filtered.length === 0 ? (
              <EmptyState icon={FileText} title="No reports yet"
                hint="Generate your first report — it will appear here with download and preview options." />
            ) : (
              <ul className="divide-y divide-edge">
                {filtered.map((r, i) => (
                  <motion.li
                    key={r.id}
                    initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                    className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
                  >
                    <div className="rounded-lg bg-surface-2 p-2">
                      <FileText className="h-4 w-4 text-primary" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-ink">{r.title}</p>
                      <p className="text-[11px] text-muted">#{r.id} · {formatDate(r.created_at)}</p>
                    </div>
                    <Badge tone="blue">{r.report_type}</Badge>
                    <Badge tone={r.status === 'completed' ? 'green' : 'amber'}>{r.status}</Badge>
                    <Badge>{r.file_format.toUpperCase()}</Badge>
                    {r.file_format === 'pdf' && (
                      <Button size="icon" variant="ghost" aria-label={`Preview report ${r.id}`}
                        onClick={() => setPreview(r)}>
                        <Eye className="h-4 w-4" />
                      </Button>
                    )}
                    <a href={reportApi.downloadUrl(r.id)} download aria-label={`Download report ${r.id}`}>
                      <Button size="icon" variant="ghost"><Download className="h-4 w-4" /></Button>
                    </a>
                  </motion.li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* PDF preview — streams the real file from the download endpoint */}
      <Dialog open={!!preview} onClose={() => setPreview(null)} title={preview?.title} panelClassName="max-w-3xl">
        {preview && (
          <iframe
            src={reportApi.downloadUrl(preview.id)}
            title={`Preview of ${preview.title}`}
            className="h-[60vh] w-full rounded-lg border border-edge bg-white"
          />
        )}
      </Dialog>
    </div>
  )
}
