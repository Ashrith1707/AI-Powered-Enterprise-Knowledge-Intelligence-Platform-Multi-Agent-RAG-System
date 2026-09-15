import { AnimatePresence, motion } from 'framer-motion'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { EmptyState, ErrorBanner, PageHeader, Spinner, StatusBadge } from '../components/ui'

const fmtBytes = (n) => {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0, v = n
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export default function Documents() {
  const [docs, setDocs] = useState(null)
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [preview, setPreview] = useState(null)   // {doc, pages}
  const [detail, setDetail] = useState(null)     // metadata drawer doc
  const fileInput = useRef(null)
  const pollTimer = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const data = await api.get('/documents?page_size=100')
      setDocs(data)
      return data
    } catch (e) {
      setError(e)
      return null
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // Poll while any document is still processing
  useEffect(() => {
    const hasActive = docs?.items?.some((d) => ['pending', 'processing', 'ocr'].includes(d.status))
    if (hasActive && !pollTimer.current) {
      pollTimer.current = setInterval(refresh, 1500)
    } else if (!hasActive && pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
    return () => {
      if (pollTimer.current) { clearInterval(pollTimer.current); pollTimer.current = null }
    }
  }, [docs, refresh])

  const uploadFiles = async (files) => {
    if (!files || files.length === 0) return
    setUploading(true)
    setUploadError(null)
    try {
      for (const file of files) {
        const form = new FormData()
        form.append('file', file)
        await api.upload('/documents/upload', form)
      }
      await refresh()
    } catch (e) {
      setUploadError(e)
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const openPreview = async (doc) => {
    try {
      const data = await api.get(`/documents/${doc.id}/content`)
      setPreview({ doc, pages: data.pages })
    } catch (e) { setError(e) }
  }

  const openDetail = async (doc) => {
    try { setDetail(await api.get(`/documents/${doc.id}`)) } catch (e) { setError(e) }
  }

  const reprocess = async (doc) => {
    try { await api.post(`/documents/${doc.id}/reprocess`); await refresh() } catch (e) { setError(e) }
  }

  const remove = async (doc) => {
    if (!window.confirm(`Delete "${doc.filename}"? Its vectors and chunks will be removed.`)) return
    try { await api.del(`/documents/${doc.id}`); await refresh() } catch (e) { setError(e) }
  }

  return (
    <div>
      <PageHeader title="Documents" subtitle="Upload, process and manage your enterprise knowledge base" />
      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      <ErrorBanner error={uploadError} onDismiss={() => setUploadError(null)} />

      {/* Upload zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); uploadFiles(e.dataTransfer.files) }}
        onClick={() => fileInput.current?.click()}
        className={`card mb-6 flex cursor-pointer flex-col items-center justify-center gap-2 border-2 border-dashed px-6 py-10 transition
          ${dragOver ? 'border-brand-500 bg-brand-600/10' : 'border-slate-700 hover:border-slate-600'}`}
      >
        <input ref={fileInput} type="file" multiple className="hidden"
               accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.tiff"
               onChange={(e) => uploadFiles(e.target.files)} />
        {uploading ? <Spinner size="h-7 w-7" /> : <div className="text-3xl">📤</div>}
        <div className="text-sm font-semibold text-slate-200">
          {uploading ? 'Uploading…' : 'Drop documents here or click to browse'}
        </div>
        <div className="text-xs text-slate-500">PDF · DOCX · TXT · MD · PNG · JPG · TIFF — max 25 MB each. Scanned files go through OCR.</div>
      </div>

      {/* Table */}
      {!docs ? (
        <div className="flex justify-center py-16"><Spinner size="h-8 w-8" /></div>
      ) : docs.items.length === 0 ? (
        <EmptyState title="No documents yet" hint="Upload your first enterprise document to build the knowledge base." />
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-950/50 text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-5 py-3">Document</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Pages / Chunks</th>
                <th className="px-4 py-3">Size</th>
                <th className="px-4 py-3">Uploaded</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {docs.items.map((d) => (
                <tr key={d.id} className="group transition hover:bg-slate-800/30">
                  <td className="max-w-[300px] px-5 py-3">
                    <button onClick={() => openDetail(d)} className="block truncate text-left font-medium text-slate-200 hover:text-brand-300">
                      {d.filename}
                    </button>
                    <div className="text-[10px] uppercase tracking-wider text-slate-600">{d.file_type}</div>
                    {['pending', 'processing', 'ocr'].includes(d.status) && (
                      <div className="mt-1.5 h-1 w-40 overflow-hidden rounded-full bg-slate-800">
                        <motion.div
                          className="h-full rounded-full bg-brand-500"
                          animate={{ width: `${Math.max(5, d.processing_progress || 5)}%` }}
                          transition={{ ease: 'easeOut' }}
                        />
                      </div>
                    )}
                    {d.status === 'failed' && d.error_message && (
                      <div className="mt-1 max-w-xs truncate text-[10px] text-red-400/80" title={d.error_message}>
                        {d.error_message}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={d.status} /></td>
                  <td className="px-4 py-3 text-slate-400">{d.page_count} / {d.chunk_count}</td>
                  <td className="px-4 py-3 text-slate-400">{fmtBytes(d.file_size)}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {d.created_at ? new Date(d.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1.5 opacity-60 transition group-hover:opacity-100">
                      {d.status === 'completed' && (
                        <button onClick={() => openPreview(d)} className="btn-secondary !px-2.5 !py-1.5 !text-xs">Preview</button>
                      )}
                      {d.status === 'failed' && (
                        <button onClick={() => reprocess(d)} className="btn-secondary !px-2.5 !py-1.5 !text-xs">Retry</button>
                      )}
                      <button onClick={() => remove(d)} className="btn-danger">Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Preview modal */}
      <AnimatePresence>
        {preview && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-6"
            onClick={() => setPreview(null)}
          >
            <motion.div
              initial={{ scale: 0.95, y: 10 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95 }}
              className="card max-h-[80vh] w-full max-w-3xl overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
                <div className="truncate text-sm font-semibold text-slate-200">{preview.doc.filename}</div>
                <button onClick={() => setPreview(null)} className="text-slate-500 hover:text-slate-300">✕</button>
              </div>
              <div className="max-h-[65vh] space-y-4 overflow-y-auto p-5">
                {preview.pages.length === 0 && <p className="text-sm text-slate-500">No extracted text.</p>}
                {preview.pages.map((p) => (
                  <div key={p.page}>
                    <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-brand-400">Page {p.page}</div>
                    <pre className="whitespace-pre-wrap rounded-lg bg-slate-950/70 p-3 font-sans text-xs leading-relaxed text-slate-300">{p.text}</pre>
                  </div>
                ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Metadata drawer */}
      <AnimatePresence>
        {detail && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/60" onClick={() => setDetail(null)}
          >
            <motion.div
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'tween', duration: 0.22 }}
              className="absolute right-0 top-0 h-full w-full max-w-md overflow-y-auto border-l border-slate-800 bg-slate-900 p-6 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-bold text-white">{detail.filename}</h3>
                  <div className="mt-1"><StatusBadge status={detail.status} /></div>
                </div>
                <button onClick={() => setDetail(null)} className="text-slate-500 hover:text-slate-300">✕</button>
              </div>

              <Section title="Extracted metadata">
                <KV k="Title" v={detail.metadata?.title} />
                <KV k="Author" v={detail.metadata?.author} />
                <KV k="Department" v={detail.metadata?.department} />
                <KV k="Category" v={detail.metadata?.category} />
                <KV k="Document date" v={detail.metadata?.document_date} />
                <KV k="Version" v={detail.metadata?.version} />
                <KV k="Doc IDs" v={(detail.metadata?.document_ids || []).join(', ')} />
                {detail.metadata?.tags?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {detail.metadata.tags.map((t) => (
                      <span key={t} className="badge bg-brand-600/15 text-brand-300">#{t}</span>
                    ))}
                  </div>
                )}
              </Section>

              <Section title="Extracted entities">
                <KV k="People" v={(detail.entities?.persons || []).join(', ')} />
                <KV k="Organizations" v={(detail.entities?.organizations || []).join(', ')} />
                <KV k="Dates" v={(detail.entities?.dates || []).slice(0, 6).join(', ')} />
                <KV k="Emails" v={(detail.entities?.emails || []).join(', ')} />
                <KV k="Money" v={(detail.entities?.monetary_values || []).join(', ')} />
                <KV k="References" v={(detail.entities?.reference_codes || []).join(', ')} />
              </Section>

              <Section title="Processing">
                <KV k="Parser" v={detail.metadata?.parser} />
                <KV k="OCR used" v={detail.ocr_used ? 'yes' : 'no'} />
                <KV k="Characters" v={(detail.char_count || 0).toLocaleString()} />
                <KV k="Chunks" v={detail.chunk_count} />
                {detail.processing_completed_at && <KV k="Completed" v={new Date(detail.processing_completed_at).toLocaleString()} />}
              </Section>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="mb-5">
      <h4 className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-500">{title}</h4>
      <div className="space-y-1.5 rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs">{children}</div>
    </div>
  )
}

function KV({ k, v }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="shrink-0 text-slate-500">{k}</span>
      <span className="truncate text-right text-slate-300" title={v || ''}>{v || '—'}</span>
    </div>
  )
}
