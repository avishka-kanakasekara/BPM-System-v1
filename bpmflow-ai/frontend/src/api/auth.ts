import { apiClient, authHeaders } from './http'
import type { CurrentUser, DemoHealthPayload } from '../types/api'

export type HealthStatus = {
  status: string
  env?: string
  database?: string
  database_url_configured?: boolean
  supabase?: string
}

export async function getHealth(): Promise<HealthStatus> {
  const response = await apiClient.get<HealthStatus>('/health')
  return response.data
}

export async function getDemoHealth(): Promise<DemoHealthPayload> {
  const response = await apiClient.get<DemoHealthPayload>('/health/demo')
  return response.data
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const headers = await authHeaders()
  const response = await apiClient.get<CurrentUser>('/api/v1/auth/me', { headers })
  return response.data
}

export async function registerAccount(payload: {
  email: string
  password: string
  full_name?: string
  role?: 'requester' | 'approver' | 'admin'
}): Promise<{ id: string; email: string; confirmed: boolean; role?: string }> {
  const response = await apiClient.post('/api/v1/auth/register', payload)
  return response.data
}

export async function confirmAccountEmail(email: string): Promise<{ ok: boolean }> {
  const response = await apiClient.post('/api/v1/auth/confirm-email', { email })
  return response.data
}
