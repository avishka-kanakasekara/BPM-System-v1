import { apiClient, authHeaders } from './http'
import type {
  BottleneckCandidate,
  ExceptionAnalytics,
  KpiReport,
  ProcessMonitoringReport,
  TimelineEvent,
  TobeRecommendationRecord,
} from '../types/api'

export async function getProcessMonitoring(processId: string): Promise<ProcessMonitoringReport> {
  const headers = await authHeaders()
  const response = await apiClient.get<ProcessMonitoringReport>(
    `/api/v1/processes/${processId}/monitoring`,
    { headers },
  )
  return response.data
}

export async function getProcessTimeline(processId: string): Promise<TimelineEvent[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<TimelineEvent[]>(
    `/api/v1/processes/${processId}/timeline`,
    { headers },
  )
  return response.data
}

export async function getProcessMonitoringKpis(processId: string): Promise<KpiReport> {
  const headers = await authHeaders()
  const response = await apiClient.get<KpiReport>(`/api/v1/processes/${processId}/kpis`, {
    headers,
  })
  return response.data
}

export async function calculateProcessKpis(processId: string): Promise<KpiReport> {
  const headers = await authHeaders()
  const response = await apiClient.post<KpiReport>(
    `/api/v1/processes/${processId}/kpis/calculate`,
    {},
    { headers },
  )
  return response.data
}

export async function getProcessBottlenecks(processId: string): Promise<BottleneckCandidate[]> {
  const headers = await authHeaders()
  const response = await apiClient.get(`/api/v1/processes/${processId}/bottlenecks`, { headers })
  return response.data
}

export async function getProcessExceptionAnalytics(
  processId: string,
): Promise<ExceptionAnalytics> {
  const headers = await authHeaders()
  const response = await apiClient.get(`/api/v1/processes/${processId}/exception-analytics`, {
    headers,
  })
  return response.data
}

export async function listTobeRecommendations(
  processId: string,
): Promise<TobeRecommendationRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<TobeRecommendationRecord[]>(
    `/api/v1/processes/${processId}/recommendations`,
    { headers },
  )
  return response.data
}

export async function generateTobeRecommendations(
  processId: string,
): Promise<TobeRecommendationRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.post<TobeRecommendationRecord[]>(
    `/api/v1/processes/${processId}/recommendations/generate`,
    {},
    { headers },
  )
  return response.data
}

export async function getTobeRecommendation(
  recommendationId: string,
): Promise<TobeRecommendationRecord> {
  const headers = await authHeaders()
  const response = await apiClient.get<TobeRecommendationRecord>(
    `/api/v1/recommendations/${recommendationId}`,
    { headers },
  )
  return response.data
}

export async function reviewTobeRecommendation(
  recommendationId: string,
  payload: { decision: 'ACCEPTED' | 'REJECTED'; comment?: string },
): Promise<TobeRecommendationRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<TobeRecommendationRecord>(
    `/api/v1/recommendations/${recommendationId}/review`,
    payload,
    { headers },
  )
  return response.data
}
