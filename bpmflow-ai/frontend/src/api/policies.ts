import { apiClient, authHeaders } from './http'

export type PolicyCategory =
  | 'PROCUREMENT'
  | 'APPROVAL'
  | 'BUDGET'
  | 'AUTHORIZATION'
  | 'SLA'
  | 'SECURITY'
  | 'FINANCE'
  | 'GENERAL'

export type PolicyVersionStatus = 'DRAFT' | 'ACTIVE' | 'ARCHIVED'

export type PolicyRule = {
  id?: string
  rule_type: string
  operator?: string | null
  threshold_value?: string | null
  currency?: string | null
  required_approval?: string | null
  required_roles?: string[]
  required_evidence?: string[]
  sla_hours?: string | null
  description?: string | null
}

export type PolicyVersionRecord = {
  id: string
  policy_id: string
  tenant_id: string
  version_label: string
  status: PolicyVersionStatus
  document_name: string
  document_type: string
  effective_from: string
  effective_to?: string | null
  uploaded_at: string
  rules: PolicyRule[]
  chunks?: unknown[]
}

export type CompanyPolicyRecord = {
  id: string
  tenant_id: string
  name: string
  category: PolicyCategory
  description?: string | null
  versions: PolicyVersionRecord[]
}

export async function listPolicies(): Promise<CompanyPolicyRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<CompanyPolicyRecord[]>('/api/v1/policies', { headers })
  return response.data
}

export async function uploadPolicy(input: {
  name: string
  category: PolicyCategory
  version_label: string
  description?: string
  document_type?: string
  activate?: boolean
  text_content?: string
  file?: File | null
  effective_from?: string
  effective_to?: string
}): Promise<CompanyPolicyRecord> {
  const headers = await authHeaders()
  const form = new FormData()
  form.append('name', input.name)
  form.append('category', input.category)
  form.append('version_label', input.version_label)
  form.append('document_type', input.document_type || 'txt')
  form.append('activate', String(input.activate ?? true))
  if (input.description) form.append('description', input.description)
  if (input.text_content) form.append('text_content', input.text_content)
  if (input.effective_from) {
    form.append('effective_from', new Date(input.effective_from).toISOString())
  }
  if (input.effective_to) {
    form.append('effective_to', new Date(input.effective_to).toISOString())
  }
  if (input.file) form.append('file', input.file)
  const response = await apiClient.post<CompanyPolicyRecord>('/api/v1/policies', form, {
    headers,
  })
  return response.data
}

export async function activatePolicyVersion(
  policyId: string,
  versionId: string,
): Promise<CompanyPolicyRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<CompanyPolicyRecord>(
    `/api/v1/policies/${policyId}/versions/${versionId}/activate`,
    {},
    { headers },
  )
  return response.data
}

export async function archivePolicyVersion(
  policyId: string,
  versionId: string,
): Promise<CompanyPolicyRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<CompanyPolicyRecord>(
    `/api/v1/policies/${policyId}/versions/${versionId}/archive`,
    {},
    { headers },
  )
  return response.data
}
