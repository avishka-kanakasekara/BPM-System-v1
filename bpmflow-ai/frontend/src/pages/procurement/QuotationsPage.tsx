import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { listProcessQuotations, listProcesses, listVendors } from '../../services/apiClient'
import type { ProcessRecord, QuotationRecord, VendorRecord } from '../../types/api'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import LineItemsTable from '../../components/procurement/LineItemsTable'
import { money, procurementErrorMessage } from '../../lib/procurement'

export default function QuotationsPage() {
  const [params, setParams] = useSearchParams()
  const selectedProcess = params.get('process') || ''
  const [processes, setProcesses] = useState<ProcessRecord[]>([])
  const [quotes, setQuotes] = useState<QuotationRecord[]>([])
  const [vendors, setVendors] = useState<VendorRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const vendorName = useMemo(() => {
    const map = new Map(vendors.map((v) => [v.vendor_id, v.legal_name]))
    return (id: string) => map.get(id) ?? null
  }, [vendors])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [procs, vendorRows] = await Promise.all([listProcesses(), listVendors().catch(() => [] as VendorRecord[])])
      setProcesses(procs)
      setVendors(vendorRows)
      if (selectedProcess) {
        setQuotes(await listProcessQuotations(selectedProcess))
      } else {
        const nested = await Promise.all(procs.map((p) => listProcessQuotations(p.id).catch(() => [] as QuotationRecord[])))
        setQuotes(nested.flat())
      }
    } catch (err) {
      setError(procurementErrorMessage(err))
      setQuotes([])
    } finally {
      setLoading(false)
    }
  }, [selectedProcess])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Quotations"
        description="Quotations are process-scoped. Count comes from persisted GET /processes/{id}/quotations. There is no public create-quotation API."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Panel title="Process filter">
        <label className="text-sm">
          Process
          <select
            className="select select-bordered mt-1 w-full max-w-lg"
            value={selectedProcess}
            onChange={(e) => {
              const value = e.target.value
              if (value) setParams({ process: value })
              else setParams({})
            }}
          >
            <option value="">All accessible processes</option>
            {processes.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <p className="mt-3 text-sm text-slate-600">
          Quotation count: <span className="font-semibold">{quotes.length}</span>
        </p>
      </Panel>
      <Panel title="Quotations">
        {loading ? (
          <div aria-busy="true" className="space-y-2">
            <Skeleton className="h-16 w-full" />
          </div>
        ) : quotes.length === 0 ? (
          <EmptyState
            title="No quotations"
            body="No persisted quotations were returned for the selected process scope."
          />
        ) : (
          <ul className="space-y-4">
            {quotes.map((q) => (
              <li key={q.quotation_id} className="rounded-lg border border-slate-200 p-4">
                <div className="flex flex-wrap justify-between gap-2">
                  <p className="font-medium">{q.quotation_number}</p>
                  <span className="text-sm text-slate-500">{q.status}</span>
                </div>
                <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Vendor</dt>
                    <dd>
                      {vendorName(q.vendor_id) ? (
                        <Link className="link" to={`/vendors/${q.vendor_id}`}>
                          {vendorName(q.vendor_id)}
                        </Link>
                      ) : q.vendor_id ? (
                        <Link className="link font-mono text-xs" to={`/vendors/${q.vendor_id}`}>
                          {q.vendor_id}
                        </Link>
                      ) : (
                        'Relationship information unavailable.'
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Process</dt>
                    <dd>
                      <Link className="link" to={`/processes/${q.process_id}`}>
                        Open process
                      </Link>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Date</dt>
                    <dd>{q.quotation_date || '—'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Total</dt>
                    <dd>{money(q.total, q.currency)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Subtotal / tax</dt>
                    <dd>
                      {money(q.subtotal, q.currency)} / {money(q.tax, q.currency)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Evidence</dt>
                    <dd>{q.evidence_id || q.document_id || '—'}</dd>
                  </div>
                </dl>
                <div className="mt-3">
                  <LineItemsTable items={q.items} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  )
}
