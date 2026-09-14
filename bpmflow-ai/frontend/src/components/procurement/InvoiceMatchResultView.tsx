import type { InvoiceMatchResult } from '../../types/api'
import { Alert } from '../ui/primitives'
import { money } from '../../lib/procurement'

export default function InvoiceMatchResultView({ result }: { result: InvoiceMatchResult | null }) {
  if (!result) {
    return <p className="text-sm text-slate-500">No matching result.</p>
  }
  const matched = result.matched || result.status === 'MATCHED'
  return (
    <div className="space-y-3">
      <Alert tone={matched ? 'success' : 'warning'}>
        <p className="font-semibold">{matched ? 'MATCHED' : result.status || 'MISMATCH'}</p>
        <p className="mt-1 text-sm">
          {matched
            ? result.invoice_id && result.purchase_order_id
              ? `Successful matching of invoice ${result.invoice_id} to purchase order ${result.purchase_order_id}.`
              : 'Successful matching of the persisted invoice to the purchase order.'
            : 'Persisted invoice and purchase order did not match.'}
        </p>
        <p className="mt-1 text-sm">
          Invoice {money(result.invoice_amount, result.currency)}
          {result.po_amount != null ? ` · PO ${money(result.po_amount, result.currency)}` : ''}
          {matched && result.matched_amount != null
            ? ` · Matched ${money(result.matched_amount, result.currency)}`
            : ''}
        </p>
      </Alert>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs uppercase text-slate-500">Vendor match</dt>
          <dd>{result.vendor_match ? 'Yes' : 'No'}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Line match</dt>
          <dd>{result.line_match ? 'Yes' : 'No'}</dd>
        </div>
      </dl>
      {!matched && (result.discrepancy_codes?.length || result.discrepancy_details?.length) ? (
        <div>
          <p className="text-xs font-medium uppercase text-slate-500">Discrepancies</p>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-sm text-rose-800">
            {(result.discrepancy_details?.length
              ? result.discrepancy_details
              : result.discrepancy_codes || []
            ).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          {result.discrepancy_codes?.length && result.discrepancy_details?.length ? (
            <p className="mt-1 text-xs text-slate-500">Types: {result.discrepancy_codes.join(', ')}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
