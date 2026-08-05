import { useMutation } from '@tanstack/react-query'
import { searchApi } from '@/api/search.api'

export function useSemanticSearch() {
  return useMutation({ mutationFn: searchApi.semantic })
}

export function useAsk() {
  return useMutation({ mutationFn: searchApi.ask })
}
