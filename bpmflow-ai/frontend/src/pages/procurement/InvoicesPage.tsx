import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { completeInvoiceMatching, createInvoice, listProcessInvoices, listProcesses, listVendors } from '../../services/apiClient'
import type { InvoiceRecord, ProcessRecord, VendorRecord } from '../../types/api'
import { useAuth } from '../../auth/AuthContext'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import InvoiceMatchResultView from '../../components/procurement/InvoiceMatchResultView'
import { invoiceMatchLabel, money, parseInvoiceMatch, procurementErrorMessage } from '../../lib/procurement'

export default function InvoicesPage() {
  const { user } = useAuth()
  const isAdmin = (user?.role || '').toLowerCase() === 'admin'
  const [params] = useSearchParams()
  const processFilter = params.get('process') || ''
  const [invoices, setInvoices] = useState<InvoiceRecord[]>([])
  const [processes, setProcesses] = useState<ProcessRecord[]>([])
  const [vendors, setVendors] = useState<VendorRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [newProcessId, setNewProcessId] = useState('')
  const [newNumber, setNewNumber] = useState('')
  const [newCurrency, setNewCurrency] = useState('USD')
  const [newTotal, setNewTotal] = useState('')

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
      const nested = await Promise.all(
        (processFilter ? (procs.some((p) => p.id === processFilter) ? procs.filter((p) => p.id === processFilter) : [{ id: processFilter } as ProcessRecord]) : procs).map((p) =>
          listProcessInvoices(p.id).catch(() => [] as InvoiceRecord[]),
        ),
      )
      setInvoices(nested.flat())
    } catch (err) {
      setError(procurementErrorMessage(err))
      setInvoices([])
    } finally {
      setLoading(false)
    }
  }, [processFilter])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function onMatch(processId: string) {
    setBusy(`match-${processId}`)
    setError(null)
    setNotice(null)
    try {
      const result = await completeInvoiceMatching(processId, {})
      setNotice(result.message || 'Matching completed using persisted invoice and PO.')
      await refresh()
    } catch (err) {
      setError(procurementErrorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    if (!user?.tenant_id) {
      setError('Tenant context is required.')
      return
    }
    setBusy('create')
    setError(null)
    try {
      await createInvoice({
        tenant_id: user.tenant_id,
        process_id: newProcessId,
        invoice_number: newNumber.trim(),
        currency: newCurrency.trim(),
        total: newTotal.trim() || null,
      })
      setNewNumber('')
      setNewTotal('')
      setNotice('Invoice persisted. Matching is a separate process action.')
      await refresh()
    } catch (err) {
      setError(procurementErrorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Invoices"
        description="Persisted invoices from GET /processes/{id}/invoices. Matching uses complete-invoice-matching without expected_* truth."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice ? <Alert tone="info">{notice}</Alert> : null}

      {isAdmin ? (
        <Panel title="Persist invoice (admin)">
          <p className="mb-3 text-sm text-slate-600">This stores an invoice. It does not mark MATCHED and does not create a PO.</p>
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => void onCreate(e)}>
            <label className="text-sm">
              Process ID
              <input
                required
                className="input input-bordered mt-1 w-full font-mono text-xs"
                value={newProcessId}
                onChange={(e) => setNewProcessId(e.target.value)}
              />
            </label>
            <label className="text-sm">
              Invoice number
              <input required className="input input-bordered mt-1 w-full" value={newNumber} onChange={(e) => setNewNumber(e.target.value)} />
            </label>
            <label className="text-sm">
              Currency
              <input required className="input input-bordered mt-1 w-full" value={newCurrency} onChange={(e) => setNewCurrency(e.target.value)} />
            </label>
            <label className="text-sm">
              Total (optional)
              <input className="input input-bordered mt-1 w-full" value={newTotal} onChange={(e) => setNewTotal(e.target.value)} />
            </label>
            <div>
              <button type="submit" className="btn btn-primary btn-sm" disabled={busy !== null}>
                Persist invoice
              </button>
            </div>
          </form>
        </Panel>
      ) : null}

      <Panel title="Invoices">
        {loading ? (
          <div aria-busy="true">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : invoices.length === 0 ? (
          <EmptyState title="No invoices" body="No persisted invoices were returned." />
        ) : (
          <ul className="space-y-4">
            {invoices.map((inv) => {
              const match = parseInvoiceMatch(inv.match_result)
              const label = invoiceMatchLabel(inv)
              return (
                <li key={inv.invoice_id} className="rounded-lg border border-slate-200 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <Link className="link text-lg font-semibold" to={`/invoices/${inv.invoice_id}`}>
                      {inv.invoice_number}
                    </Link>
                    <span className="text-sm">{label || inv.status}</span>
                  </div>
                  <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
                    <div>
                      <dt className="text-xs uppercase text-slate-500">Total</dt>
                      <dd>{money(inv.total, inv.currency)}</dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase text-slate-500">Vendor</dt>
                      <dd>
                        {inv.vendor_id ? (
                          <Link className="link" to={`/vendors/${inv.vendor_id}`}>
                            {vendorName(inv.vendor_id) || inv.vendor_id}
                          </Link>
                        ) : (
                          'Relationship information unavailable.'
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase text-slate-500">PO</dt>
                      <dd>
                        {inv.purchase_order_id ? (
                          <Link className="link" to={`/purchase-orders/${inv.process_id}`}>
                            View purchase order
                          </Link>
                        ) : (
                          'Relationship information unavailable.'
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase text-slate-500">Process</dt>
                      <dd>
                        <Link className="link" to={`/processes/${inv.process_id}`}>
                          {processes.find((p) => p.id === inv.process_id)?.name || 'Open process'}
                        </Link>
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase text-slate-500">Invoice date</dt>
                      <dd>{inv.invoice_date || '—'}</dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase text-slate-500">Received</dt>
                      <dd>{inv.received_at || '—'}</dd>
                    </div>
                  </dl>
                  {match ? <div className="mt-3"><InvoiceMatchResultView result={match} /></div> : null}
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm mt-3"
                    disabled={busy !== null}
                    onClick={() => void onMatch(inv.process_id)}
                  >
                    {busy === `match-${inv.process_id}` ? 'Matching…' : 'Match persisted invoice'}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </Panel>
    </div>
  )
}
