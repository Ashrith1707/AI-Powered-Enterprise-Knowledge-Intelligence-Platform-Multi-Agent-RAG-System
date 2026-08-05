import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '@/api/analytics.api'

export function useDashboard() {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: analyticsApi.dashboard,
    refetchInterval: 10000,
  })
}

export function useSearchAnalytics(days = 30) {
  return useQuery({
    queryKey: ['searchAnalytics', days],
    queryFn: () => analyticsApi.searches(days),
    refetchInterval: 30000,
  })
}

export function useAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: analyticsApi.agents,
    staleTime: 5 * 60_000, // registry rarely changes
  })
}

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: analyticsApi.health })
}
