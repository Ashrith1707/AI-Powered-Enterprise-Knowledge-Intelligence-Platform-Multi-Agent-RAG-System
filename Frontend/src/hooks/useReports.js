import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { reportApi } from '@/api/report.api'

export function useReports() {
  return useQuery({ queryKey: ['reports'], queryFn: reportApi.list })
}

export function useCreateReport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: reportApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports'] }),
  })
}
