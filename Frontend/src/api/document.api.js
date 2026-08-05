import { http } from '@/api/client'

export const documentApi = {
  list: () => http.get('/documents').then((r) => r.data),

  get: (id) => http.get(`/documents/${id}`).then((r) => r.data),

  pages: (id) => http.get(`/documents/${id}/pages`).then((r) => r.data),

  /**
   * onProgress receives { percent, loaded, total } while the file streams up.
   * Pass an AbortSignal to make the upload cancelable.
   */
  upload: (file, { onProgress, signal } = {}) => {
    const form = new FormData()
    form.append('file', file)
    return http
      .post('/documents/upload', form, {
        signal,
        onUploadProgress: (e) => {
          if (onProgress && e.total) {
            onProgress({
              percent: Math.round((e.loaded / e.total) * 100),
              loaded: e.loaded,
              total: e.total,
            })
          }
        },
      })
      .then((r) => r.data)
  },

  remove: (id) => http.delete(`/documents/${id}`).then((r) => r.data),

  patch: (id, changes) => http.patch(`/documents/${id}`, changes).then((r) => r.data),

  /** Downloads the original file with auth, then triggers a browser save. */
  download: async (id, filename) => {
    const res = await http.get(`/documents/${id}/download`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },
}
