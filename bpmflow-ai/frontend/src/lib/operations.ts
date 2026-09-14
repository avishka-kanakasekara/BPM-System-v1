export function operationsErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  const detailText =
    typeof detail === 'string'
      ? detail
      : detail && typeof detail === 'object' && 'message' in detail
        ? String((detail as { message: unknown }).message)
        : ''
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to perform this action."
  if (status === 404) return 'The requested record was not found.'
  if (status === 409) return detailText || 'This action is not valid for the current record state.'
  if (status === 422) return detailText || 'The request could not be validated.'
  if (status === 503) return 'The service is temporarily unavailable.'
  return detailText || (err as Error).message || 'Request failed'
}

export function durationLabel(value: string | number | null | undefined): string {
  if (value == null || value === '') return 'Duration unavailable'
  return `${value} s`
}

export function isExceptionActionable(status: string | null | undefined): boolean {
  const key = (status || '').toLowerCase()
  return key === 'open' || key === 'in_progress'
}

export function formatEventType(eventType: string): string {
  return eventType
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}
