/**
 * Manages a client-side upload queue with real progress, cancellation and
 * retry. Upload = HTTP transfer only; after 201 the item moves to
 * "processing" and the backend pipeline status (polled via useDocuments)
 * takes over as the source of truth.
 */
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'
import { documentApi } from '@/api/document.api'
import { ACCEPTED_EXTENSIONS, fileTypeFromName, MAX_UPLOAD_MB } from '@/utils/constants'

let nextId = 1

export function useUploadQueue() {
  const [items, setItems] = useState([])
  const controllers = useRef(new Map())
  const qc = useQueryClient()

  const patch = useCallback((id, updates) => {
    setItems((prev) =>
      prev.map((it) =>
        it.id === id ? { ...it, ...(typeof updates === 'function' ? updates(it) : updates) } : it,
      ),
    )
  }, [])

  const start = useCallback(async (item) => {
    const controller = new AbortController()
    controllers.current.set(item.id, controller)
    patch(item.id, { status: 'uploading', progress: 0, error: null, startedAt: Date.now() })
    try {
      const res = await documentApi.upload(item.file, {
        signal: controller.signal,
        onProgress: ({ percent, loaded, total }) => {
          patch(item.id, (it) => {
            const elapsed = (Date.now() - it.startedAt) / 1000
            const speed = elapsed > 0.2 ? loaded / elapsed : 0 // bytes/sec
            return {
              progress: percent,
              speed,
              eta: speed > 0 ? Math.ceil((total - loaded) / speed) : null,
            }
          })
        },
      })
      patch(item.id, { status: 'processing', progress: 100, documentId: res.document.id })
      qc.invalidateQueries({ queryKey: ['documents'] })
    } catch (err) {
      const canceled = /cancel/i.test(err.message)
      patch(item.id, {
        status: canceled ? 'canceled' : 'error',
        error: canceled ? null : err.message,
      })
    } finally {
      controllers.current.delete(item.id)
    }
  }, [patch, qc])

  const addFiles = useCallback((fileList) => {
    const accepted = []
    for (const file of Array.from(fileList)) {
      const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
      const item = {
        id: nextId++,
        file,
        name: file.name,
        size: file.size,
        fileType: fileTypeFromName(file.name),
        status: 'queued',
        progress: 0,
        speed: 0,
        eta: null,
        error: null,
        documentId: null,
      }
      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        item.status = 'error'
        item.error = `Unsupported type "${ext}". Allowed: ${ACCEPTED_EXTENSIONS.join(', ')}`
      } else if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
        item.status = 'error'
        item.error = `Exceeds the ${MAX_UPLOAD_MB} MB limit`
      } else if (file.size === 0) {
        item.status = 'error'
        item.error = 'File is empty'
      }
      accepted.push(item)
    }
    setItems((prev) => [...accepted, ...prev])
    accepted.filter((i) => i.status === 'queued').forEach((i) => start(i))
  }, [start])

  const cancel = useCallback((id) => controllers.current.get(id)?.abort(), [])
  const retry = useCallback((item) => start(item), [start])
  const remove = useCallback(
    (id) => setItems((prev) => prev.filter((it) => it.id !== id)),
    [],
  )
  const clearFinished = useCallback(
    () =>
      setItems((prev) =>
        prev.filter((it) => ['uploading', 'queued'].includes(it.status)),
      ),
    [],
  )

  return { items, addFiles, cancel, retry, remove, clearFinished }
}
