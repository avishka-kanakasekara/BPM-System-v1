import type { ProcessContext } from '../../types/api'
import { EmptyState, Panel } from '../ui/primitives'
import { asRecord, displayText, factSourceLabel } from './helpers'

function Row({ label, value, hint }: { label: string; value: string | null | undefined; hint?: string | null }) {
  if (!value) return null
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-800">
        {value}
        {hint ? <span className="mt-0.5 block text-xs text-slate-500">{hint}</span> : null}
      </dd>
    </div>
  )
}

export default function ProcessContextPanel({
  context,
}: {
  context: ProcessContext | Record<string, unknown> | null | undefined
}) {
  const ctx = (asRecord(context) || context) as ProcessContext | null
  if (!ctx || typeof ctx !== 'object') {
    return (
      <Panel title="Process Context">
        <EmptyState
          title="No process context yet"
          body="Verified facts from discovery and the company directory will appear here. Nothing is invented in the browser."
        />
      </Panel>
    )
  }

  const requester = ctx.requester
  const purchase = ctx.purchase
  const budget = ctx.budget
  const quotations = ctx.quotations ?? []
  const evidence = ctx.evidence ?? []
  const policy = ctx.policy
  const risk = ctx.risk
  const approver = ctx.approver

  const hasAnything =
    Boolean(requester?.name || requester?.email || purchase?.description || purchase?.amount) ||
    quotations.length > 0 ||
    evidence.length > 0

  return (
    <Panel title="Process Context">
      {!hasAnything ? (
        <p className="text-sm text-slate-600">
          Process context is present but no displayable facts were returned. Evidence is not fabricated.
        </p>
      ) : (
        <dl className="grid gap-4 sm:grid-cols-2">
          <Row label="Requester" value={displayText(requester?.name) || displayText(requester?.email)} />
          <Row label="Department" value={displayText(requester?.department)} />
          <Row
            label="Purchase"
            value={displayText(purchase?.description)}
            hint={factSourceLabel(purchase?.amount_source)}
          />
          <Row
            label="Amount"
            value={
              purchase?.amount != null
                ? `${purchase.amount}${purchase.currency ? ` ${purchase.currency}` : ''}`
                : null
            }
            hint={factSourceLabel(purchase?.amount_source)}
          />
          <Row label="Vendor" value={displayText(purchase?.vendor_name) || displayText(purchase?.vendor_id)} />
          <Row
            label="Budget available"
            value={
              budget?.available_amount != null
                ? `${budget.available_amount}${budget.currency ? ` ${budget.currency}` : ''}`
                : null
            }
            hint={factSourceLabel(budget?.source)}
          />
          <Row label="Quotations" value={quotations.length ? String(quotations.length) : null} />
          <Row label="Evidence items" value={evidence.length ? String(evidence.length) : null} />
          <Row label="Policy IDs" value={policy?.policy_ids?.length ? policy.policy_ids.join(', ') : null} />
          <Row label="Approver" value={displayText(approver?.email) || displayText(approver?.role)} />
          <Row label="Risk summary" value={displayText(risk?.risk_level)} />
        </dl>
      )}
      {evidence.length > 0 ? (
        <ul className="mt-4 space-y-1 text-xs text-slate-600">
          {evidence.slice(0, 8).map((item) => (
            <li key={item.evidence_id} className="break-all font-mono">
              {item.evidence_id}
              {item.document_id ? ` · doc ${item.document_id}` : ''}
              {item.field ? ` · ${item.field}` : ''}
            </li>
          ))}
        </ul>
      ) : null}
    </Panel>
  )
}
