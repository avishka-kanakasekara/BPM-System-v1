export default function EvidenceList({
  items,
}: {
  items?: Array<{ field?: string; value?: unknown; source?: string; workflow_step_id?: string | null }> | string[] | null
}) {
  if (!items || items.length === 0) {
    return <p className="text-sm text-slate-500">Evidence unavailable</p>
  }
  return (
    <ul className="list-disc space-y-1 pl-4 text-sm">
      {items.map((item, idx) => {
        if (typeof item === 'string') {
          return <li key={`${item}-${idx}`}>{item}</li>
        }
        const value = item.value == null ? '' : typeof item.value === 'string' ? item.value : JSON.stringify(item.value)
        return (
          <li key={`${item.field}-${idx}`}>
            {item.field}
            {value ? `: ${value}` : ''}
            {item.source ? ` (${item.source})` : ''}
          </li>
        )
      })}
    </ul>
  )
}
