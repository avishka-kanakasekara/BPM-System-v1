import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getProcessPurchaseOrder, getVendor } from '../../services/apiClient'
import type { PurchaseOrderRecord } from '../../types/api'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import { PurchaseOrderDetailPanel } from './PurchaseOrdersPage'
import { isNotFoundError, procurementErrorMessage } from '../../lib/procurement'

export default function PurchaseOrderDetailPage() {
  const { processId = '' } = useParams()
  const [po, setPo] = useState<PurchaseOrderRecord | null>(null)
  const [vendorLabel, setVendorLabel] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!processId) return
    setLoading(true)
    setError(null)
    try {
      const row = await getProcessPurchaseOrder(processId)
      setPo(row)
      if (row.vendor_id) {
        try {
          const vendor = await getVendor(row.vendor_id)
          setVendorLabel(vendor.legal_name)
        } catch {
          setVendorLabel(null)
        }
      }
    } catch (err) {
      setPo(null)
      setError(isNotFoundError(err) ? 'No purchase order yet for this process.' : procurementErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [processId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  if (loading && !po) {
    return (
      <div aria-busy="true">
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Link to="/purchase-orders" className="text-sm font-medium text-slate-500">
        ← Purchase orders
      </Link>
      <PageHeader title={po?.po_number || 'Purchase order'} description="Persisted process purchase order. Creation is not available here." />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Panel>
        {po ? (
          <PurchaseOrderDetailPanel po={po} vendorLabel={vendorLabel} />
        ) : (
          <EmptyState title="No purchase order yet" body="Execute the authorized Create Purchase Order workflow step when the process is in workflow execution." />
        )}
      </Panel>
    </div>
  )
}
