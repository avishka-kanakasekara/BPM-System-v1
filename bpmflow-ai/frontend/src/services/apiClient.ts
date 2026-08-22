import axios, { AxiosRequestConfig } from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_URL,
})

apiClient.interceptors.request.use((config: AxiosRequestConfig) => {
  const headers = config.headers ?? {}
  if (config.data instanceof FormData) {
    if (typeof headers.delete === 'function') {
      headers.delete('Content-Type')
    } else {
      delete (headers as Record<string, unknown>)['Content-Type']
    }
  } else if (!headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }
  config.headers = headers
  return config
})

export type AgentMessage = {
  message_id: string
  process_id: string
  sender: string
  status: string
  overall_confidence: number
  payload: {
    process_name?: string | null
    activities?: Array<{
      name: string
      actor?: string | null
      system?: string | null
      avg_duration?: number | null
      entry_conditions?: string[]
      exit_conditions?: string[]
    }>
    rules?: Array<{ description: string; controls_activity?: string | null }>
    dependencies?: Array<{ predecessor: string; successor: string }>
    exceptions?: Array<{ kind: string; description: string; case_id?: string | null }>
    missing_or_contradictory_fields?: string[]
    discovery_errors?: string[]
  }
}

export type ProcessSummary = {
  process_id: string
  name: string
  status: string
  discovery_status?: string | null
  overall_confidence?: number | null
  activity_count: number
  created_at?: string | null
}

export async function discoverProcess(files: File[]): Promise<AgentMessage> {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  const response = await apiClient.post<AgentMessage>('/api/v1/agent1/discover', form)
  return response.data
}

export async function listDiscoveredProcesses(): Promise<ProcessSummary[]> {
  const response = await apiClient.get<ProcessSummary[]>('/api/v1/agent1/processes')
  return response.data
}

export default apiClient
