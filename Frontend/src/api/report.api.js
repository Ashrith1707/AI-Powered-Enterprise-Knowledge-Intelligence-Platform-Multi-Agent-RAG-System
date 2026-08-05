import { http } from '@/api/client'

export const reportApi = {
  list: () => http.get('/reports').then((r) => r.data),
  create: (payload) => http.post('/reports', payload).then((r) => r.data),
  downloadUrl: (id) => `/api/reports/${id}/download`,
}
