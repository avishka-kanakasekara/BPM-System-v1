export function unavailable(value: string | number | null | undefined): string {
  if (value == null || value === '') return 'Unavailable'
  return String(value)
}

export function formatPct(value: string | number | null | undefined): string {
  if (value == null || value === '') return 'Unavailable'
  return `${value}%`
}
