import type { InvoiceMatchResult, InvoiceRecord } from '../types/api'
import { asRecord } from '../components/process-cockpit/helpers'

export function procurementErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  const detailText =
    typeof detail === 'string'
      ? detail
      : detail && typeof detail === 'object' && 'message' in detail
        ? String((detail as { message: unknown }).message)
        : ''
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to perform this procurement action."
  if (status === 404) return 'The requested procurement record was not found.'
  if (status === 409) return 'This procurement action is not valid for the current process state.'
  if (status === 422) return detailText || 'The procurement request could not be validated.'
  if (status === 503) return 'The procurement service is temporarily unavailable.'
  return detailText || (err as Error).message || 'Request failed'
}

export function isNotFoundError(err: unknown): boolean {
  return (err as { response?: { status?: number } })?.response?.status === 404
}

export function money(amount: string | number | null | undefined, currency?: string | null): string {
  if (amount == null || amount === '') return '—'
  return currency ? `${amount} ${currency}` : String(amount)
}

export function parseInvoiceMatch(value: unknown): InvoiceMatchResult | null {
  const obj = asRecord(value)
  if (!obj) return null
  const matched = obj.matched
  const status = typeof obj.status === 'string' ? obj.status : null
  if (typeof matched !== 'boolean' && !status) return null
  const codes = Array.isArray(obj.discrepancy_codes)
    ? obj.discrepancy_codes.filter((x): x is string => typeof x === 'string')
    : []
  const details = Array.isArray(obj.discrepancy_details)
    ? obj.discrepancy_details.filter((x): x is string => typeof x === 'string')
    : []
  return {
    invoice_id: String(obj.invoice_id ?? ''),
    purchase_order_id: String(obj.purchase_order_id ?? ''),
    process_id: String(obj.process_id ?? ''),
    tenant_id: String(obj.tenant_id ?? ''),
    status: status || (matched ? 'MATCHED' : 'MISMATCH'),
    matched: typeof matched === 'boolean' ? matched : status === 'MATCHED',
    discrepancy_codes: codes,
    discrepancy_details: details,
    matched_amount: (obj.matched_amount as string | number | null) ?? null,
    invoice_amount: (obj.invoice_amount as string | number | null) ?? null,
    po_amount: (obj.po_amount as string | number | null) ?? null,
    currency: typeof obj.currency === 'string' ? obj.currency : null,
    vendor_match: Boolean(obj.vendor_match),
    line_match: Boolean(obj.line_match),
    evidence_refs: Array.isArray(obj.evidence_refs)
      ? obj.evidence_refs.filter((x): x is string => typeof x === 'string')
      : [],
    trace_id: typeof obj.trace_id === 'string' ? obj.trace_id : null,
    amount_tolerance: typeof obj.amount_tolerance === 'string' ? obj.amount_tolerance : undefined,
  }
}

export function invoiceMatchLabel(invoice: InvoiceRecord): string | null {
  const parsed = parseInvoiceMatch(invoice.match_result)
  if (parsed) return parsed.matched || parsed.status === 'MATCHED' ? 'MATCHED' : parsed.status || 'MISMATCH'
  if (invoice.status === 'MATCHED' || invoice.status === 'MISMATCH') return invoice.status
  return null
}
