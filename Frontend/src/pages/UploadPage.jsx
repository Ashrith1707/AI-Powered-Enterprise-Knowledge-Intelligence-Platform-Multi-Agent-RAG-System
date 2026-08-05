import { AnimatePresence, motion } from 'framer-motion'
import {
  CheckCircle2, CloudUpload, FileWarning, FolderOpen, RotateCcw, Trash2, X,
} from 'lucide-react'
import { useCallback, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState } from '@/components/shared/States'
import { PipelineTracker } from '@/components/upload/PipelineTracker'
import { StatusBadge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/components/ui/toast'
import { useDocuments } from '@/hooks/useDocuments'
import { useUploadQueue } from '@/hooks/useUploadQueue'
import { cn } from '@/utils/cn'
import { ACCEPT_ATTR, FILE_TYPE_META, MAX_UPLOAD_MB } from '@/utils/constants'
import { formatBytes, formatRelative } from '@/utils/format'

function formatSpeed(bps) {
  if (!bps) return ''
  return `${formatBytes(bps)}/s`
}

function QueueItem({ item, doc, onCancel, onRetry, onRemove }) {
  const meta = FILE_TYPE_META[item.fileType] ?? FILE_TYPE_META.txt
  const Icon = meta.icon

  // After the HTTP upload finishes, the backend pipeline is the truth.
  const pipelineStatus = item.documentId ? doc?.status ?? 'uploaded' : null
  const finished = pipelineStatus === 'indexed'
  const pipelineFailed = pipelineStatus === 'failed'

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.2 }}
      className="flex flex-col gap-2.5 rounded-xl border border-edge bg-surface p-4"
    >
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-surface-2 p-2">
          <Icon className="h-4.5 w-4.5" style={{ color: meta.color }} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">{item.name}</p>
          <p className="text-[11px] text-muted">
            {formatBytes(item.size)}
            {item.status === 'uploading' && item.speed > 0 && (
              <> · {formatSpeed(item.speed)}{item.eta != null && ` · ~${item.eta}s left`}</>
            )}
          </p>
        </div>

        {/* Right-side status / actions */}
        <div className="flex items-center gap-1.5">
          {item.status === 'uploading' && (
            <Button size="icon" variant="ghost" aria-label="Cancel upload" onClick={() => onCancel(item.id)}>
              <X className="h-4 w-4" />
            </Button>
          )}
          {(item.status === 'error' || item.status === 'canceled') && !item.documentId && (
            <>
              <Button size="sm" variant="secondary" onClick={() => onRetry(item)}>
                <RotateCcw className="h-3.5 w-3.5" /> Retry
              </Button>
              <Button size="icon" variant="ghost" aria-label="Remove from queue" onClick={() => onRemove(item.id)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </>
          )}
          {finished && (
            <motion.span
              initial={{ scale: 0.4, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: 'spring', stiffness: 380, damping: 18 }}
            >
              <CheckCircle2 className="h-5 w-5 text-success" />
            </motion.span>
          )}
        </div>
      </div>

      {/* Transfer progress bar */}
      {item.status === 'uploading' && (
        <div className="h-1.5 overflow-hidden rounded-full bg-surface-2" role="progressbar"
          aria-valuenow={item.progress} aria-valuemin={0} aria-valuemax={100}>
          <motion.div
            className="h-full rounded-full bg-primary"
            animate={{ width: `${item.progress}%` }}
            transition={{ ease: 'easeOut', duration: 0.2 }}
          />
        </div>
      )}

      {/* Pipeline stages (real backend status, live-polled) */}
      {item.documentId && !pipelineFailed && <PipelineTracker status={pipelineStatus} />}

      {(item.error || pipelineFailed) && (
        <p className="flex items-start gap-1.5 text-xs text-danger">
          <FileWarning className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {item.error ?? doc?.error_message ?? 'Processing failed'}
        </p>
      )}
    </motion.li>
  )
}

export default function UploadPage() {
  const { items, addFiles, cancel, retry, remove, clearFinished } = useUploadQueue()
  const { data: docs } = useDocuments()
  const { push } = useToast()
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)
  const docById = new Map((docs ?? []).map((d) => [d.id, d]))

  const handleFiles = useCallback((files) => {
    if (!files?.length) return
    addFiles(files)
    push(`${files.length} file${files.length > 1 ? 's' : ''} added to the queue`, 'info')
  }, [addFiles, push])

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const recent = (docs ?? []).slice(0, 5)
  const hasFinished = items.some((i) => !['uploading', 'queued'].includes(i.status))

  return (
    <div>
      <PageHeader
        title="Upload documents"
        description="Files enter the ingestion pipeline: parsing, OCR, metadata, chunking and vector indexing."
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {/* Dropzone */}
          <motion.div
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            role="button"
            tabIndex={0}
            aria-label="Upload files by dropping them here or browsing"
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
            onClick={() => inputRef.current?.click()}
            className={cn(
              'flex cursor-pointer flex-col items-center justify-center rounded-card border-2 border-dashed p-10 text-center transition-all duration-200',
              dragging
                ? 'scale-[1.01] border-primary bg-primary-soft'
                : 'border-edge bg-surface hover:border-primary/50 hover:bg-surface-2/50',
            )}
          >
            <motion.div
              animate={dragging ? { y: -4, scale: 1.08 } : { y: 0, scale: 1 }}
              className="mb-4 rounded-2xl bg-primary-soft p-4"
            >
              <CloudUpload className="h-7 w-7 text-primary" />
            </motion.div>
            <p className="text-sm font-medium text-ink">
              {dragging ? 'Drop to upload' : 'Drag & drop files here'}
            </p>
            <p className="mt-1 text-xs text-muted">
              or <span className="font-medium text-primary">browse</span> — up to {MAX_UPLOAD_MB} MB per file
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-1.5">
              {Object.values(FILE_TYPE_META).map(({ label }) => (
                <span key={label} className="rounded-full border border-edge bg-surface px-2.5 py-0.5 text-[10px] font-medium text-ink-2">
                  {label}
                </span>
              ))}
            </div>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT_ATTR}
              className="hidden"
              onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }}
            />
          </motion.div>

          {/* Queue */}
          {items.length > 0 && (
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Upload queue</CardTitle>
                  <CardDescription>{items.length} file{items.length > 1 ? 's' : ''} this session</CardDescription>
                </div>
                {hasFinished && (
                  <Button size="sm" variant="ghost" onClick={clearFinished}>Clear finished</Button>
                )}
              </CardHeader>
              <CardContent>
                <ul className="space-y-2.5">
                  <AnimatePresence mode="popLayout">
                    {items.map((item) => (
                      <QueueItem
                        key={item.id}
                        item={item}
                        doc={item.documentId ? docById.get(item.documentId) : null}
                        onCancel={cancel}
                        onRetry={retry}
                        onRemove={remove}
                      />
                    ))}
                  </AnimatePresence>
                </ul>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Recent uploads */}
        <Card className="h-fit">
          <CardHeader>
            <div>
              <CardTitle>Recent uploads</CardTitle>
              <CardDescription>Latest documents in the knowledge base</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            {recent.length === 0 ? (
              <EmptyState icon={FolderOpen} title="Nothing here yet"
                hint="Your first upload will appear here with its live pipeline status." />
            ) : (
              <ul className="space-y-3">
                {recent.map((d) => (
                  <li key={d.id} className="flex items-center gap-2.5">
                    <div className="min-w-0 flex-1">
                      <Link to="/documents" className="block truncate text-xs font-medium text-ink hover:text-primary">
                        {d.filename}
                      </Link>
                      <p className="text-[10px] text-muted">{formatRelative(d.uploaded_at)} · {formatBytes(d.file_size)}</p>
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
