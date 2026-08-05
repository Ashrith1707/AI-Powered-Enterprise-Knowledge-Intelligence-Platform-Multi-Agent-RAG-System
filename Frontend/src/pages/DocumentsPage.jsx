import { AnimatePresence, motion } from 'framer-motion'
import {
  ChevronLeft, ChevronRight, Copy, Download, Eye, FileText, LayoutGrid,
  List, MoreHorizontal, Pencil, Pin, PinOff, RefreshCcw, Search, Trash2, UploadCloud,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { documentApi } from '@/api/document.api'
import { DocumentDrawer } from '@/components/documents/DocumentDrawer'
import { PageHeader } from '@/components/shared/PageHeader'
import { ConfirmDialog, EmptyState, ErrorState } from '@/components/shared/States'
import { Badge, StatusBadge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog } from '@/components/ui/dialog'
import { Dropdown, DropdownItem, DropdownSeparator } from '@/components/ui/dropdown'
import { Input, Label } from '@/components/ui/input'
import { TableSkeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/toast'
import { useDebounce } from '@/hooks/useDebounce'
import { useDeleteDocument, useDocuments, usePatchDocument } from '@/hooks/useDocuments'
import { usePinnedDocuments } from '@/hooks/useLocalStorage'
import { cn } from '@/utils/cn'
import { DOC_SORTERS, FILE_TYPE_META } from '@/utils/constants'
import { formatBytes, formatRelative } from '@/utils/format'

const PAGE_SIZE = 9

function Select({ value, onChange, children, 'aria-label': ariaLabel }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={ariaLabel}
      className="h-9 rounded-lg border border-edge bg-surface px-2.5 text-xs font-medium text-ink-2 focus:border-primary focus:outline-none"
    >
      {children}
    </select>
  )
}

function DocActions({ doc, isPinned, onPin, onPreview, onDelete, onRename }) {
  const { push } = useToast()
  return (
    <Dropdown
      trigger={
        <Button size="icon" variant="ghost" aria-label={`Actions for ${doc.filename}`}>
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      }
    >
      <DropdownItem icon={Eye} onClick={onPreview}>View details</DropdownItem>
      <DropdownItem
        icon={Copy}
        onClick={() => {
          navigator.clipboard.writeText(String(doc.id))
          push('Document ID copied', 'success')
        }}
      >
        Copy document ID
      </DropdownItem>
      <DropdownItem icon={isPinned ? PinOff : Pin} onClick={onPin}>
        {isPinned ? 'Unpin' : 'Pin to top'}
      </DropdownItem>
      <DropdownSeparator />
      <DropdownItem icon={Download} onClick={async () => {
        try {
          await documentApi.download(doc.id, doc.filename)
        } catch (err) {
          push(err.message, 'error')
        }
      }}>
        Download original
      </DropdownItem>
      <DropdownItem icon={Pencil} onClick={onRename}>Rename / edit</DropdownItem>
      <DropdownSeparator />
      <DropdownItem icon={Trash2} className="text-danger" onClick={onDelete}>
        Delete
      </DropdownItem>
    </Dropdown>
  )
}

function DocCard({ doc, index, isPinned, onPin, onPreview, onDelete, onRename }) {
  const meta = FILE_TYPE_META[doc.file_type] ?? FILE_TYPE_META.txt
  const Icon = meta.icon
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.04, 0.3), duration: 0.25 }}
    >
      <Card className="group h-full transition-all hover:-translate-y-0.5 hover:shadow-md">
        <CardContent className="flex h-full flex-col p-4">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-surface-2 p-2.5">
              <Icon className="h-5 w-5" style={{ color: meta.color }} />
            </div>
            <div className="min-w-0 flex-1">
              <button
                onClick={onPreview}
                className="block w-full truncate text-left text-sm font-medium text-ink hover:text-primary"
                title={doc.filename}
              >
                {isPinned && <Pin className="mr-1 inline h-3 w-3 text-primary" />}
                {doc.filename}
              </button>
              <p className="mt-0.5 text-[11px] text-muted">
                {formatBytes(doc.file_size)} · {doc.page_count} pages · {formatRelative(doc.uploaded_at)}
              </p>
            </div>
            <DocActions doc={doc} isPinned={isPinned} onPin={onPin} onPreview={onPreview}
              onDelete={onDelete} onRename={onRename} />
          </div>
          <div className="mt-auto flex items-center gap-1.5 pt-3">
            <StatusBadge status={doc.status} />
            <Badge tone="blue">{doc.category}</Badge>
            {doc.used_ocr && <Badge tone="amber">OCR</Badge>}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}

export default function DocumentsPage() {
  const { data: docs, isLoading, error, refetch, isFetching } = useDocuments()
  const deleteMutation = useDeleteDocument()
  const { pinned, toggle: togglePin, isPinned } = usePinnedDocuments()
  const { push } = useToast()

  const [params] = useSearchParams()
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [category, setCategory] = useState('all')
  const [status, setStatus] = useState('all')
  const [sort, setSort] = useState('newest')
  const [view, setView] = useState('grid')
  const [page, setPage] = useState(1)
  const [previewId, setPreviewId] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [renameTarget, setRenameTarget] = useState(null)
  const [renameForm, setRenameForm] = useState({ filename: '', category: '' })
  const patchMutation = usePatchDocument()

  const debouncedQuery = useDebounce(query)

  const categories = useMemo(
    () => [...new Set((docs ?? []).map((d) => d.category))].sort(),
    [docs],
  )

  const filtered = useMemo(() => {
    let list = docs ?? []
    if (debouncedQuery) {
      const q = debouncedQuery.toLowerCase()
      list = list.filter((d) => d.filename.toLowerCase().includes(q))
    }
    if (category !== 'all') list = list.filter((d) => d.category === category)
    if (status !== 'all') list = list.filter((d) => d.status === status)
    list = [...list].sort(DOC_SORTERS[sort].fn)
    // Pinned documents float to the top, keeping their relative order.
    return [
      ...list.filter((d) => pinned.includes(d.id)),
      ...list.filter((d) => !pinned.includes(d.id)),
    ]
  }, [docs, debouncedQuery, category, status, sort, pinned])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const visible = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  const confirmDelete = async () => {
    const target = deleteTarget
    setDeleteTarget(null)
    try {
      await deleteMutation.mutateAsync(target.id)
      push(`"${target.filename}" deleted`, 'success')
    } catch (err) {
      push(err.message, 'error')
    }
  }

  if (error) return <ErrorState message={error.message} onRetry={refetch} />

  return (
    <div>
      <PageHeader
        title="Documents"
        description={`${docs?.length ?? 0} documents in the knowledge base`}
        actions={
          <Link to="/upload">
            <Button><UploadCloud className="h-4 w-4" /> Upload</Button>
          </Link>
        }
      />

      {/* Toolbar */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-52 flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input
            value={query}
            onChange={(e) => { setQuery(e.target.value); setPage(1) }}
            placeholder="Search by filename…"
            className="h-9 pl-9"
            aria-label="Search documents"
          />
        </div>
        <Select value={category} onChange={(v) => { setCategory(v); setPage(1) }} aria-label="Filter by category">
          <option value="all">All categories</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
        <Select value={status} onChange={(v) => { setStatus(v); setPage(1) }} aria-label="Filter by status">
          <option value="all">All statuses</option>
          {['indexed', 'parsing', 'parsed', 'uploaded', 'failed'].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </Select>
        <Select value={sort} onChange={setSort} aria-label="Sort documents">
          {Object.entries(DOC_SORTERS).map(([key, { label }]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </Select>

        <div className="ml-auto flex items-center gap-1">
          <Button size="icon" variant="ghost" aria-label="Refresh list"
            onClick={() => refetch()} className={cn(isFetching && 'animate-spin')}>
            <RefreshCcw className="h-4 w-4" />
          </Button>
          <div className="flex rounded-lg border border-edge p-0.5">
            <button
              aria-label="Grid view" aria-pressed={view === 'grid'}
              onClick={() => setView('grid')}
              className={cn('rounded-md p-1.5', view === 'grid' ? 'bg-surface-2 text-ink' : 'text-muted')}
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
            <button
              aria-label="List view" aria-pressed={view === 'list'}
              onClick={() => setView('list')}
              className={cn('rounded-md p-1.5', view === 'list' ? 'bg-surface-2 text-ink' : 'text-muted')}
            >
              <List className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <Card><TableSkeleton rows={6} /></Card>
      ) : visible.length === 0 ? (
        <Card>
          <EmptyState
            icon={FileText}
            title={debouncedQuery || category !== 'all' || status !== 'all'
              ? 'No documents match your filters'
              : 'No documents yet'}
            hint={debouncedQuery ? 'Try a different search term or clear the filters.'
              : 'Upload your first document to start building the knowledge base.'}
            action={!debouncedQuery && (
              <Link to="/upload"><Button size="sm"><UploadCloud className="h-3.5 w-3.5" /> Upload now</Button></Link>
            )}
          />
        </Card>
      ) : view === 'grid' ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <AnimatePresence mode="popLayout">
            {visible.map((d, i) => (
              <DocCard
                key={d.id} doc={d} index={i}
                isPinned={isPinned(d.id)}
                onPin={() => togglePin(d.id)}
                onPreview={() => setPreviewId(d.id)}
                onDelete={() => setDeleteTarget(d)}
                onRename={() => { setRenameTarget(d); setRenameForm({ filename: d.filename, category: d.category }) }}
              />
            ))}
          </AnimatePresence>
        </div>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-edge text-left text-xs text-muted">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Category</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Pages</th>
                <th className="px-4 py-3 font-medium">Size</th>
                <th className="px-4 py-3 font-medium">Uploaded</th>
                <th className="px-2 py-3" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {visible.map((d) => {
                const meta = FILE_TYPE_META[d.file_type] ?? FILE_TYPE_META.txt
                const Icon = meta.icon
                return (
                  <tr key={d.id} className="border-b border-edge last:border-0 hover:bg-surface-2/50">
                    <td className="px-4 py-2.5">
                      <button onClick={() => setPreviewId(d.id)}
                        className="flex items-center gap-2 font-medium text-ink hover:text-primary">
                        <Icon className="h-4 w-4 shrink-0" style={{ color: meta.color }} />
                        {isPinned(d.id) && <Pin className="h-3 w-3 shrink-0 text-primary" />}
                        <span className="max-w-56 truncate">{d.filename}</span>
                      </button>
                    </td>
                    <td className="px-4 py-2.5"><Badge tone="blue">{d.category}</Badge></td>
                    <td className="px-4 py-2.5"><StatusBadge status={d.status} /></td>
                    <td className="px-4 py-2.5 text-ink-2">{d.page_count}</td>
                    <td className="px-4 py-2.5 text-ink-2">{formatBytes(d.file_size)}</td>
                    <td className="px-4 py-2.5 text-muted">{formatRelative(d.uploaded_at)}</td>
                    <td className="px-2 py-2.5">
                      <DocActions doc={d} isPinned={isPinned(d.id)}
                        onPin={() => togglePin(d.id)}
                        onPreview={() => setPreviewId(d.id)}
                        onDelete={() => setDeleteTarget(d)}
                        onRename={() => { setRenameTarget(d); setRenameForm({ filename: d.filename, category: d.category }) }} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}

      {/* Pagination */}
      {pageCount > 1 && (
        <div className="mt-4 flex items-center justify-between text-xs text-muted">
          <p>
            Showing {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, filtered.length)} of {filtered.length}
          </p>
          <div className="flex items-center gap-1.5">
            <Button size="sm" variant="secondary" disabled={safePage === 1}
              onClick={() => setPage(safePage - 1)} aria-label="Previous page">
              <ChevronLeft className="h-3.5 w-3.5" /> Prev
            </Button>
            <span className="px-2 font-medium text-ink">{safePage} / {pageCount}</span>
            <Button size="sm" variant="secondary" disabled={safePage === pageCount}
              onClick={() => setPage(safePage + 1)} aria-label="Next page">
              Next <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      <DocumentDrawer documentId={previewId} onClose={() => setPreviewId(null)} />

      <Dialog
        open={!!renameTarget}
        onClose={() => setRenameTarget(null)}
        title="Edit document"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRenameTarget(null)}>Cancel</Button>
            <Button loading={patchMutation.isPending} onClick={async () => {
              try {
                await patchMutation.mutateAsync({
                  id: renameTarget.id,
                  changes: {
                    filename: renameForm.filename.trim() || renameTarget.filename,
                    category: renameForm.category.trim() || renameTarget.category,
                  },
                })
                push('Document updated', 'success')
                setRenameTarget(null)
              } catch (err) {
                push(err.message, 'error')
              }
            }}>
              Save
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <Label htmlFor="rn-file">Filename</Label>
            <Input id="rn-file" value={renameForm.filename}
              onChange={(e) => setRenameForm((f) => ({ ...f, filename: e.target.value }))} />
          </div>
          <div>
            <Label htmlFor="rn-cat">Category</Label>
            <Input id="rn-cat" value={renameForm.category}
              onChange={(e) => setRenameForm((f) => ({ ...f, category: e.target.value }))} />
          </div>
        </div>
      </Dialog>
      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
        busy={deleteMutation.isPending}
        title="Delete document?"
        description={`"${deleteTarget?.filename}" and all of its pages, metadata, chunks and vectors will be removed permanently.`}
      />
    </div>
  )
}
