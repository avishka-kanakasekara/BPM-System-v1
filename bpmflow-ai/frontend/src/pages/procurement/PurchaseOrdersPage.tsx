import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getProcessPurchaseOrder, listProcesses, listVendors } from '../../services/apiClient'
import type { ProcessRecord, PurchaseOrderRecord, VendorRecord } from '../../types/api'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import LineItemsTable from '../../components/procurement/LineItemsTable'
import { formatDateTime } from '../../components/process-cockpit/helpers'
import { isNotFoundError, money, procurementErrorMessage } from '../../lib/procurement'

export default function PurchaseOrdersPage() {
  const [orders, setOrders] = useState<PurchaseOrderRecord[]>([])
  const [vendors, setVendors] = useState<VendorRecord[]>([])
  const [processes, setProcesses] = useState<ProcessRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const vendorName = useMemo(() => {
    const map = new Map(vendors.map((v) => [v.vendor_id, v.legal_name]))
    return (id: string) => map.get(id) ?? null
  }, [vendors])
  const processName = useMemo(() => {
    const map = new Map(processes.map((p) => [p.id, p.name]))
    return (id: string) => map.get(id) ?? null
  }, [processes])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [procs, vendorRows] = await Promise.all([listProcesses(), listVendors().catch(() => [] as VendorRecord[])])
      setProcesses(procs)
      setVendors(vendorRows)
      const results = await Promise.all(
        procs.map(async (p) => {
          try {
            return await getProcessPurchaseOrder(p.id)
          } catch (err) {
            if (isNotFoundError(err)) return null
            throw err
          }
        }),
      )
      setOrders(results.filter((row): row is PurchaseOrderRecord => row != null))
    } catch (err) {
      setError(procurementErrorMessage(err))
      setOrders([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Purchase orders"
        description="Persisted POs from GET /processes/{id}/purchase-order. There is no frontend Create PO action — POs are created by an authorized WorkflowStep."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Panel>
        {loading ? (
          <div aria-busy="true">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : orders.length === 0 ? (
          <EmptyState
            title="No purchase order yet"
            body="No persisted purchase orders were returned. Direct requester PO creation is not offered."
          />
        ) : (
          <ul className="space-y-4">
            {orders.map((po) => (
              <li key={po.purchase_order_id} className="rounded-lg border border-slate-200 p-4">
                <div className="flex flex-wrap justify-between gap-2">
                  <Link className="link text-lg font-semibold" to={`/purchase-orders/${po.process_id}`}>
                    {po.po_number}
                  </Link>
                  <span className="text-sm">{po.status}</span>
                </div>
                <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Process</dt>
                    <dd>
                      <Link className="link" to={`/processes/${po.process_id}`}>
                        {processName(po.process_id) || po.process_id}
                      </Link>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Vendor</dt>
                    <dd>
                      {po.vendor_id ? (
                        <Link className="link" to={`/vendors/${po.vendor_id}`}>
                          {vendorName(po.vendor_id) || po.vendor_id}
                        </Link>
                      ) : (
                        'Relationship information unavailable.'
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Total</dt>
                    <dd>{money(po.total, po.currency)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Subtotal / tax</dt>
                    <dd>
                      {money(po.subtotal, po.currency)} / {money(po.tax, po.currency)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Created</dt>
                    <dd>{formatDateTime(po.created_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Selected quotation</dt>
                    <dd>
                      {po.selected_quotation_id ? (
                        <Link className="link font-mono text-xs" to={`/quotations?process=${po.process_id}`}>
                          {po.selected_quotation_id}
                        </Link>
                      ) : (
                        'Relationship information unavailable.'
                      )}
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  )
}

export function PurchaseOrderDetailPanel({ po, vendorLabel }: { po: PurchaseOrderRecord; vendorLabel?: string | null }) {
  return (
    <div className="space-y-4">
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs uppercase text-slate-500">PO number</dt>
          <dd>{po.po_number}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Status</dt>
          <dd>{po.status}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Total</dt>
          <dd>{money(po.total, po.currency)}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Created</dt>
          <dd>{formatDateTime(po.created_at)}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Vendor</dt>
          <dd>
            {po.vendor_id ? (
              <Link className="link" to={`/vendors/${po.vendor_id}`}>
                {vendorLabel || po.vendor_id}
              </Link>
            ) : (
              'Relationship information unavailable.'
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Workflow</dt>
          <dd className="break-all font-mono text-xs">
            {po.workflow_plan_id || po.workflow_step_id
              ? `${po.workflow_plan_id ?? '—'} / ${po.workflow_step_id ?? '—'}`
              : 'Relationship information unavailable.'}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Selected quotation</dt>
          <dd>
            {po.selected_quotation_id ? (
              <Link className="link font-mono text-xs" to={`/quotations?process=${po.process_id}`}>
                {po.selected_quotation_id}
              </Link>
            ) : (
              'Relationship information unavailable.'
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Process</dt>
          <dd>
            <Link className="link" to={`/processes/${po.process_id}`}>
              Open process
            </Link>
          </dd>
        </div>
      </dl>
      <LineItemsTable items={po.items} />
    </div>
  )
}
