import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getVendor } from '../../services/apiClient'
import type { VendorRecord } from '../../types/api'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import { procurementErrorMessage } from '../../lib/procurement'

export default function VendorDetailPage() {
  const { vendorId = '' } = useParams()
  const [vendor, setVendor] = useState<VendorRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!vendorId) return
    setLoading(true)
    setError(null)
    try {
      setVendor(await getVendor(vendorId))
    } catch (err) {
      setVendor(null)
      setError(procurementErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [vendorId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  if (loading && !vendor) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  if (!vendor) {
    return (
      <div className="space-y-4">
        <Link to="/vendors" className="text-sm font-medium text-slate-500">
          ← Vendors
        </Link>
        {error ? <Alert tone="error">{error}</Alert> : <EmptyState title="Vendor not found" body="No vendor record was returned." />}
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => void refresh()}>
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Link to="/vendors" className="text-sm font-medium text-slate-500">
        ← Vendors
      </Link>
      <PageHeader title={vendor.legal_name} description={vendor.vendor_code} />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Panel title="Vendor">
        <dl className="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase text-slate-500">Vendor ID</dt>
            <dd className="mt-1 break-all font-mono text-xs">{vendor.vendor_id}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Status</dt>
            <dd className="mt-1">{vendor.status}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Phone</dt>
            <dd className="mt-1">{vendor.phone || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Website</dt>
            <dd className="mt-1">{vendor.website || '—'}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-xs uppercase text-slate-500">Notes</dt>
            <dd className="mt-1">{vendor.notes || '—'}</dd>
          </div>
        </dl>
        <p className="mt-4 text-sm text-slate-500">
          Quotations and purchase orders are process-scoped. Open a process to follow vendor → quotation → PO → invoice
          relationships when those IDs are present on the records.
        </p>
      </Panel>
    </div>
  )
}
