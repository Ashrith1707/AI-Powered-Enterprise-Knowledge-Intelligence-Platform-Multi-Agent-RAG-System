/** Single source of truth for file-type + pipeline metadata. */
import { FileImage, FileText, FileType2, ScrollText } from 'lucide-react'

export const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg']
export const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(',')
export const MAX_UPLOAD_MB = 50

export const FILE_TYPE_META = {
  pdf: { icon: ScrollText, label: 'PDF', color: 'var(--chart-1)' },
  docx: { icon: FileType2, label: 'Word', color: 'var(--chart-2)' },
  txt: { icon: FileText, label: 'Text', color: 'var(--chart-3)' },
  image: { icon: FileImage, label: 'Scan', color: 'var(--chart-4)' },
}

export function fileTypeFromName(name) {
  const ext = name.slice(name.lastIndexOf('.')).toLowerCase()
  if (ext === '.pdf') return 'pdf'
  if (ext === '.docx') return 'docx'
  if (ext === '.txt') return 'txt'
  if (['.png', '.jpg', '.jpeg'].includes(ext)) return 'image'
  return null
}

/**
 * The backend pipeline reports: uploaded → parsing → parsed → indexed | failed.
 * These are the REAL stages (see backend/app/services/pipeline_service.py) —
 * we render exactly what the API emits, no invented sub-stages.
 */
export const PIPELINE_STAGES = [
  { key: 'uploaded', label: 'Queued' },
  { key: 'parsing', label: 'Parsing & OCR' },
  { key: 'parsed', label: 'Chunking & Embedding' },
  { key: 'indexed', label: 'Indexed' },
]

export function stageIndex(status) {
  const i = PIPELINE_STAGES.findIndex((s) => s.key === status)
  return i === -1 ? PIPELINE_STAGES.length - 1 : i
}

export const DOC_SORTERS = {
  newest: { label: 'Newest first', fn: (a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at) },
  oldest: { label: 'Oldest first', fn: (a, b) => new Date(a.uploaded_at) - new Date(b.uploaded_at) },
  name: { label: 'Name A–Z', fn: (a, b) => a.filename.localeCompare(b.filename) },
  size: { label: 'Largest first', fn: (a, b) => b.file_size - a.file_size },
  pages: { label: 'Most pages', fn: (a, b) => b.page_count - a.page_count },
}
