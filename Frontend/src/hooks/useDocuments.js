import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { documentApi } from '@/api/document.api'

const KEY = ['documents']

export function useDocuments(options = {}) {
  return useQuery({
    queryKey: KEY,
    queryFn: documentApi.list,
    // Poll while any document is still processing so statuses update live.
    refetchInterval: (query) => {
      const docs = query.state.data
      const busy = docs?.some((d) => d.status === 'uploaded' || d.status === 'parsing')
      return busy ? 3000 : 15000
    },
    ...options,
  })
}

export function useDocument(id) {
  return useQuery({
    queryKey: ['documents', id],
    queryFn: () => documentApi.get(id),
    enabled: !!id,
  })
}

export function useDocumentPages(id) {
  return useQuery({
    queryKey: ['documents', id, 'pages'],
    queryFn: () => documentApi.pages(id),
    enabled: !!id,
  })
}

export function usePatchDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, changes }) => documentApi.patch(id, changes),
    onSuccess: (updated) => {
      qc.setQueryData(KEY, (docs) => docs?.map((d) => (d.id === updated.id ? updated : d)))
      qc.invalidateQueries({ queryKey: ['documents', updated.id] })
    },
  })
}

export function useUploadDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, onProgress }) => documentApi.upload(file, onProgress),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDeleteDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: documentApi.remove,
    // Optimistic update: drop the row immediately, roll back on error.
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: KEY })
      const previous = qc.getQueryData(KEY)
      qc.setQueryData(KEY, (docs) => docs?.filter((d) => d.id !== id))
      return { previous }
    },
    onError: (_err, _id, ctx) => qc.setQueryData(KEY, ctx.previous),
    onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
