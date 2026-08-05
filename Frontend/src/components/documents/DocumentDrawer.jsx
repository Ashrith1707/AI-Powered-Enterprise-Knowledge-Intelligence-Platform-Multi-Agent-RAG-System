/** Right-side metadata drawer: full document detail + extracted page preview. */
import { AnimatePresence, motion } from 'framer-motion'
import { Copy, FileText, Hash, Languages, Tags, X } from 'lucide-react'
import { createPortal } from 'react-dom'
import { StatusBadge, Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/toast'
import { useDocument, useDocumentPages } from '@/hooks/useDocuments'
import { formatBytes, formatDate } from '@/utils/format'
import { highlightTerms } from '@/utils/highlight'

function Row({ label, children }) {
  return (
    <div className="flex items-start justify-between gap-3 py-2 text-xs">
      <span className="shrink-0 text-muted">{label}</span>
      <span className="text-right font-medium text-ink">{children}</span>
    </div>
  )
}

function Section({ title, icon: Icon, children }) {
  return (
    <div className="border-t border-edge px-5 py-4">
      <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">
        {Icon && <Icon className="h-3.5 w-3.5" />} {title}
      </p>
      {children}
    </div>
  )
}

export function DocumentDrawer({ documentId, onClose, highlight }) {
  const { data: doc, isLoading } = useDocument(documentId)
  const { data: pages } = useDocumentPages(documentId)
  const { push } = useToast()

  const meta = doc?.doc_metadata
  const entities = meta?.entities ?? {}

  return createPortal(
    <AnimatePresence>
      {documentId && (
        <motion.div className="fixed inset-0 z-50" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden />
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label="Document details"
            className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col bg-surface shadow-2xl"
            initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
            transition={{ type: 'tween', duration: 0.22, ease: 'easeOut' }}
          >
            {/* Header */}
            <div className="flex items-start gap-3 border-b border-edge p-5">
              <div className="rounded-xl bg-primary-soft p-2.5">
                <FileText className="h-5 w-5 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                {isLoading ? (
                  <Skeleton className="h-5 w-48" />
                ) : (
                  <>
                    <p className="break-words text-sm font-semibold text-ink">{doc?.filename}</p>
                    <div className="mt-1.5 flex items-center gap-2">
                      <StatusBadge status={doc?.status} />
                      <Badge tone="blue">{doc?.category}</Badge>
                    </div>
                  </>
                )}
              </div>
              <button
                onClick={onClose}
                aria-label="Close details"
                className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink"
              >
                <X className="h-4.5 w-4.5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              {/* Facts */}
              <div className="px-5 py-3">
                <Row label="Document ID">
                  <button
                    className="inline-flex items-center gap-1 text-primary hover:underline"
                    onClick={() => {
                      navigator.clipboard.writeText(String(doc?.id))
                      push('Document ID copied', 'success')
                    }}
                  >
                    #{doc?.id} <Copy className="h-3 w-3" />
                  </button>
                </Row>
                <Row label="Type">{doc?.file_type?.toUpperCase()}</Row>
                <Row label="Size">{formatBytes(doc?.file_size)}</Row>
                <Row label="Pages">{doc?.page_count}</Row>
                <Row label="OCR applied">{doc?.used_ocr ? 'Yes' : 'No'}</Row>
                <Row label="Uploaded">{formatDate(doc?.uploaded_at)}</Row>
                <Row label="Processed">{formatDate(doc?.processed_at)}</Row>
                {doc?.error_message && (
                  <p className="mt-2 rounded-lg bg-danger-soft p-2.5 text-xs text-danger">{doc.error_message}</p>
                )}
              </div>

              {/* Extracted metadata */}
              {meta && (
                <>
                  <Section title="Extracted metadata" icon={Languages}>
                    <Row label="Title">{meta.title || '—'}</Row>
                    <Row label="Language">{meta.language?.toUpperCase()}</Row>
                    {meta.summary && (
                      <p className="mt-2 rounded-lg bg-surface-2 p-3 text-xs leading-relaxed text-ink-2">
                        {meta.summary}
                      </p>
                    )}
                  </Section>

                  {meta.keywords?.length > 0 && (
                    <Section title="Keywords" icon={Tags}>
                      <div className="flex flex-wrap gap-1.5">
                        {meta.keywords.map((k) => <Badge key={k}>{k}</Badge>)}
                      </div>
                    </Section>
                  )}

                  {Object.values(entities).some((v) => v?.length) && (
                    <Section title="Entities" icon={Hash}>
                      {Object.entries(entities).map(([kind, values]) =>
                        values?.length ? (
                          <div key={kind} className="mb-2">
                            <p className="mb-1 text-[10px] uppercase tracking-wide text-muted">{kind}</p>
                            <div className="flex flex-wrap gap-1.5">
                              {values.slice(0, 8).map((v) => <Badge key={v} tone="neutral">{v}</Badge>)}
                            </div>
                          </div>
                        ) : null,
                      )}
                    </Section>
                  )}
                </>
              )}

              {/* Page preview */}
              {pages?.length > 0 && (
                <Section title={`Content preview (${pages.length} pages)`} icon={FileText}>
                  <div className="space-y-3">
                    {pages.slice(0, 2).map((p) => (
                      <div key={p.page_number} className="rounded-lg border border-edge bg-surface-2/50 p-3">
                        <p className="mb-1 text-[10px] font-semibold uppercase text-muted">
                          Page {p.page_number}{p.ocr_applied && ' · OCR'} · {p.word_count} words
                        </p>
                        <p className="line-clamp-6 whitespace-pre-wrap text-xs leading-relaxed text-ink-2">
                          {p.text ? (highlight ? highlightTerms(p.text, highlight) : p.text) : '(no extractable text)'}
                        </p>
                      </div>
                    ))}
                  </div>
                </Section>
              )}
            </div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}
