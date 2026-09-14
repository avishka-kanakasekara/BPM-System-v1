import { apiClient, authHeaders } from './http'
import type { DocumentIngestResponse, EvidenceChunk, SearchHit } from '../types/api'

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

export type ProcessDetail = ProcessSummary & {
  process_json?: Record<string, unknown> | null
  description?: string | null
  workflow?: Array<{
    order: number
    title: string
    actor?: string | null
    system?: string | null
    avg_duration?: number | null
    status?: string
    description?: string | null
  }>
}

export async function discoverProcess(
  files: File[],
  processId?: string | null,
): Promise<AgentMessage> {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  if (processId) {
    form.append('process_id', processId)
  }
  const headers = await authHeaders()
  const response = await apiClient.post<AgentMessage>('/api/v1/agent1/discover', form, { headers })
  return response.data
}

export async function listDiscoveredProcesses(): Promise<ProcessSummary[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<ProcessSummary[]>('/api/v1/agent1/processes', { headers })
  return response.data
}

export async function getDiscoveredProcess(processId: string): Promise<ProcessDetail> {
  const headers = await authHeaders()
  const response = await apiClient.get<ProcessDetail>(`/api/v1/agent1/processes/${processId}`, {
    headers,
  })
  return response.data
}

export async function ingestDocument(
  file: File,
  options: { document_type?: string; source?: string; version?: string } = {},
): Promise<DocumentIngestResponse> {
  const form = new FormData()
  form.append('files', file)
  if (options.document_type) form.append('document_type', options.document_type)
  if (options.source) form.append('source', options.source)
  if (options.version) form.append('version', options.version)
  const headers = await authHeaders()
  const response = await apiClient.post<DocumentIngestResponse>('/api/v1/agent1/documents', form, {
    headers,
  })
  return response.data
}

export async function getDocument(documentId: string): Promise<Record<string, unknown>> {
  const headers = await authHeaders()
  const response = await apiClient.get(`/api/v1/agent1/documents/${documentId}`, { headers })
  return response.data
}

export async function searchDocuments(payload: {
  query: string
  top_k?: number
  document_id?: string
}): Promise<SearchHit[]> {
  const headers = await authHeaders()
  const response = await apiClient.post<SearchHit[]>('/api/v1/agent1/search', payload, { headers })
  return response.data
}

export async function getEvidence(chunkId: string): Promise<EvidenceChunk> {
  const headers = await authHeaders()
  const response = await apiClient.get<EvidenceChunk>(`/api/v1/agent1/evidence/${chunkId}`, {
    headers,
  })
  return response.data
}
