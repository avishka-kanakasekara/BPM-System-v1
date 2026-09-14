import { apiClient, authHeaders } from './http'
import type {
  ApproverCandidate,
  DepartmentRecord,
  EmployeeRecord,
  InvoiceRecord,
  RoleRecord,
  SodComparison,
  ToolRegistryRecord,
  VendorRecord,
} from '../types/api'

export async function listEmployees(): Promise<EmployeeRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<EmployeeRecord[]>('/api/v1/company/employees', { headers })
  return response.data
}

export async function getEmployee(employeeId: string): Promise<EmployeeRecord> {
  const headers = await authHeaders()
  const response = await apiClient.get<EmployeeRecord>(
    `/api/v1/company/employees/${employeeId}`,
    { headers },
  )
  return response.data
}

export async function createEmployee(payload: {
  tenant_id: string
  employee_number: string
  full_name: string
  email: string
  department_id: string
  role_id: string
  phone?: string | null
  manager_employee_id?: string | null
  status?: 'active' | 'inactive'
  skill_codes?: string[]
}): Promise<EmployeeRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<EmployeeRecord>('/api/v1/company/employees', payload, {
    headers,
  })
  return response.data
}

export async function listDepartments(): Promise<DepartmentRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<DepartmentRecord[]>('/api/v1/company/departments', {
    headers,
  })
  return response.data
}

export async function listCompanyRoles(): Promise<RoleRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<RoleRecord[]>('/api/v1/company/roles', { headers })
  return response.data
}

export async function listDirectoryApprovers(params: {
  approval_type: string
  amount?: string
  currency?: string
  department_id?: string
  required_authority?: string
}): Promise<ApproverCandidate[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<ApproverCandidate[]>('/api/v1/company/approvers', {
    headers,
    params,
  })
  return response.data
}

export async function compareSod(params: {
  requester_employee_id: string
  approver_employee_id?: string
}): Promise<SodComparison> {
  const headers = await authHeaders()
  const response = await apiClient.get<SodComparison>('/api/v1/company/sod', {
    headers,
    params,
  })
  return response.data
}

export async function listVendors(): Promise<VendorRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<VendorRecord[]>('/api/v1/vendors', { headers })
  return response.data
}

export async function getVendor(vendorId: string): Promise<VendorRecord> {
  const headers = await authHeaders()
  const response = await apiClient.get<VendorRecord>(`/api/v1/vendors/${vendorId}`, { headers })
  return response.data
}

export async function getInvoice(invoiceId: string): Promise<InvoiceRecord> {
  const headers = await authHeaders()
  const response = await apiClient.get<InvoiceRecord>(`/api/v1/invoices/${invoiceId}`, { headers })
  return response.data
}

export async function createVendor(payload: {
  tenant_id: string
  vendor_code: string
  legal_name: string
  vendor_id?: string
  status?: 'active' | 'inactive'
  phone?: string | null
  website?: string | null
  notes?: string | null
}): Promise<VendorRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<VendorRecord>('/api/v1/vendors', payload, { headers })
  return response.data
}

export async function createInvoice(payload: {
  tenant_id: string
  process_id: string
  invoice_number: string
  currency: string
  purchase_order_id?: string | null
  vendor_ref?: string | null
  total?: string | number | null
  subtotal?: string | number | null
  tax?: string | number
  invoice_id?: string
  evidence_id?: string | null
  items?: Array<{
    description: string
    quantity: string | number
    unit_price: string | number
    purchase_order_item_id?: string | null
  }>
}): Promise<InvoiceRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<InvoiceRecord>('/api/v1/invoices', payload, { headers })
  return response.data
}

export async function listRegistryTools(): Promise<ToolRegistryRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<ToolRegistryRecord[]>('/api/v1/tools', { headers })
  return response.data
}

export async function resolveRegistryTool(payload: {
  action_code: string
  tool_category?: string
  step_type?: string
}): Promise<ToolRegistryRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<ToolRegistryRecord>('/api/v1/tools/resolve', payload, {
    headers,
  })
  return response.data
}

export async function getRegistryTool(toolId: string): Promise<ToolRegistryRecord> {
  const headers = await authHeaders()
  const response = await apiClient.get<ToolRegistryRecord>(`/api/v1/tools/${toolId}`, { headers })
  return response.data
}

export async function registerRegistryTool(payload: {
  tool_name: string
  tool_category: string
  action_code: string
  implementation_key: string
  display_name?: string | null
  description?: string | null
  version?: string
  enabled?: boolean
  requires_authorization?: boolean
  allowed_step_types?: string[]
  required_permissions?: string[]
  input_schema?: Record<string, unknown>
  output_schema?: Record<string, unknown>
  configuration?: Record<string, unknown>
}): Promise<ToolRegistryRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<ToolRegistryRecord>('/api/v1/tools', payload, { headers })
  return response.data
}

export async function enableRegistryTool(toolId: string): Promise<ToolRegistryRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<ToolRegistryRecord>(
    `/api/v1/tools/${toolId}/enable`,
    {},
    { headers },
  )
  return response.data
}

export async function disableRegistryTool(toolId: string): Promise<ToolRegistryRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<ToolRegistryRecord>(
    `/api/v1/tools/${toolId}/disable`,
    {},
    { headers },
  )
  return response.data
}
