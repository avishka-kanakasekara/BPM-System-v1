import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { completeInvoiceMatching, getInvoice, getVendor, listProcessExceptions } from '../../services/apiClient'
import type { ExceptionRecord, InvoiceRecord, VendorRecord } from '../../types/api'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import InvoiceMatchResultView from '../../components/procurement/InvoiceMatchResultView'
import LineItemsTable from '../../components/procurement/LineItemsTable'
import { invoiceMatchLabel, money, parseInvoiceMatch, procurementErrorMessage } from '../../lib/procurement'

export default function InvoiceDetailPage() {
  const { invoiceId = '' } = useParams()
  const [invoice, setInvoice] = useState<InvoiceRecord | null>(null)
  const [vendor, setVendor] = useState<VendorRecord | null>(null)
  const [exceptions, setExceptions] = useState<ExceptionRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    if (!invoiceId) return
    setLoading(true)
    setError(null)
    try {
      const row = await getInvoice(invoiceId)
      setInvoice(row)
      if (row.vendor_id) {
        try {
          setVendor(await getVendor(row.vendor_id))
        } catch {
          setVendor(null)
        }
      }
      try {
        const rows = await listProcessExceptions(row.process_id)
        setExceptions(rows.filter((e) => e.type === 'INVOICE_MISMATCH' || e.exception_code === 'INVOICE_MISMATCH'))
      } catch {
        setExceptions([])
      }
    } catch (err) {
      setInvoice(null)
      setError(procurementErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [invoiceId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function onMatch() {
    if (!invoice) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const result = await completeInvoiceMatching(invoice.process_id, {})
      setNotice(result.message || 'Matching used persisted invoice and PO.')
      await refresh()
    } catch (err) {
      setError(procurementErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (loading && !invoice) {
    return (
      <div aria-busy="true">
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  if (!invoice) {
    return (
      <div className="space-y-4">
        <Link to="/invoices" className="text-sm font-medium text-slate-500">
          ← Invoices
        </Link>
        {error ? <Alert tone="error">{error}</Alert> : <EmptyState title="Invoice not found" body="No invoice record was returned." />}
      </div>
    )
  }

  const match = parseInvoiceMatch(invoice.match_result)

  return (
    <div className="space-y-6">
      <Link to="/invoices" className="text-sm font-medium text-slate-500">
        ← Invoices
      </Link>
      <PageHeader title={invoice.invoice_number} description={invoiceMatchLabel(invoice) || invoice.status} />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice ? <Alert tone="info">{notice}</Alert> : null}
      <Panel title="Invoice">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase text-slate-500">Total</dt>
            <dd>{money(invoice.total, invoice.currency)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Subtotal / tax</dt>
            <dd>
              {money(invoice.subtotal, invoice.currency)} / {money(invoice.tax, invoice.currency)}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Vendor</dt>
            <dd>
              {invoice.vendor_id ? (
                <Link className="link" to={`/vendors/${invoice.vendor_id}`}>
                  {vendor?.legal_name || invoice.vendor_id}
                </Link>
              ) : (
                'Relationship information unavailable.'
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Purchase order</dt>
            <dd>
              {invoice.purchase_order_id ? (
                <Link className="link" to={`/purchase-orders/${invoice.process_id}`}>
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
              <Link className="link" to={`/processes/${invoice.process_id}`}>
                Open process
              </Link>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Invoice date</dt>
            <dd>{invoice.invoice_date || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Received</dt>
            <dd>{invoice.received_at || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Evidence</dt>
            <dd>{invoice.evidence_id || invoice.document_id || '—'}</dd>
          </div>
        </dl>
        <div className="mt-4">
          <LineItemsTable items={invoice.items} />
        </div>
        <button type="button" className="btn btn-primary btn-sm mt-4" disabled={busy} onClick={() => void onMatch()}>
          {busy ? 'Matching…' : 'Match persisted invoice'}
        </button>
      </Panel>
      <Panel title="Matching result">
        <InvoiceMatchResultView result={match} />
        {exceptions.length > 0 ? (
          <p className="mt-3 text-sm">
            Exception:{' '}
            <Link className="link" to={`/processes/${invoice.process_id}`}>
              {exceptions[0].title || exceptions[0].exception_code || exceptions[0].id}
            </Link>
          </p>
        ) : null}
      </Panel>
    </div>
  )
}
