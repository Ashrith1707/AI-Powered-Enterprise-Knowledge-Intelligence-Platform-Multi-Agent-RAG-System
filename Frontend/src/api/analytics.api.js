import { http } from '@/api/client'

export const analyticsApi = {
  dashboard: () => http.get('/analytics/dashboard').then((r) => r.data),
  searches: (days = 30) => http.get(`/analytics/searches?days=${days}`).then((r) => r.data),
  agents: () => http.get('/agents').then((r) => r.data),
  health: () => http.get('/health').then((r) => r.data),
}
