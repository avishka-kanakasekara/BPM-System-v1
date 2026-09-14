import { FormEvent, useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { createVendor, listVendors } from '../../services/apiClient'
import type { VendorRecord } from '../../types/api'
import { useAuth } from '../../auth/AuthContext'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import { procurementErrorMessage } from '../../lib/procurement'

export default function VendorsPage() {
  const { user } = useAuth()
  const isAdmin = (user?.role || '').toLowerCase() === 'admin'
  const [rows, setRows] = useState<VendorRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [vendorCode, setVendorCode] = useState('')
  const [legalName, setLegalName] = useState('')
  const [phone, setPhone] = useState('')
  const [website, setWebsite] = useState('')
  const [notes, setNotes] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setRows(await listVendors())
    } catch (err) {
      setError(procurementErrorMessage(err))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    if (!user?.tenant_id) {
      setError('Tenant context is required.')
      return
    }
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await createVendor({
        tenant_id: user.tenant_id,
        vendor_code: vendorCode.trim(),
        legal_name: legalName.trim(),
        phone: phone.trim() || null,
        website: website.trim() || null,
        notes: notes.trim() || null,
      })
      setVendorCode('')
      setLegalName('')
      setPhone('')
      setWebsite('')
      setNotes('')
      setNotice('Vendor created.')
      await refresh()
    } catch (err) {
      setError(procurementErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Vendors"
        description="Tenant-scoped vendor records. Creation is an admin API operation."
        actions={
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void refresh()}>
            Refresh
          </button>
        }
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice ? <Alert tone="success">{notice}</Alert> : null}

      {isAdmin ? (
        <Panel title="Add vendor">
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => void onCreate(e)}>
            <label className="text-sm">
              Vendor code
              <input
                required
                className="input input-bordered mt-1 w-full"
                value={vendorCode}
                onChange={(e) => setVendorCode(e.target.value)}
              />
            </label>
            <label className="text-sm">
              Legal name
              <input
                required
                className="input input-bordered mt-1 w-full"
                value={legalName}
                onChange={(e) => setLegalName(e.target.value)}
              />
            </label>
            <label className="text-sm">
              Phone
              <input className="input input-bordered mt-1 w-full" value={phone} onChange={(e) => setPhone(e.target.value)} />
            </label>
            <label className="text-sm">
              Website
              <input className="input input-bordered mt-1 w-full" value={website} onChange={(e) => setWebsite(e.target.value)} />
            </label>
            <label className="text-sm sm:col-span-2">
              Notes
              <textarea className="textarea textarea-bordered mt-1 w-full" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </label>
            <div className="sm:col-span-2">
              <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
                {busy ? 'Saving…' : 'Create vendor'}
              </button>
            </div>
          </form>
        </Panel>
      ) : null}

      <Panel title="Directory">
        {loading ? (
          <div className="space-y-2" aria-busy="true">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState title="No vendors" body="No tenant-scoped vendors were returned. Records are not invented in the browser." />
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Legal name</th>
                  <th>Status</th>
                  <th>Phone</th>
                  <th>Website</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((vendor) => (
                  <tr key={vendor.vendor_id}>
                    <td>
                      <Link className="link link-hover font-medium" to={`/vendors/${vendor.vendor_id}`}>
                        {vendor.vendor_code}
                      </Link>
                    </td>
                    <td>{vendor.legal_name}</td>
                    <td>{vendor.status}</td>
                    <td>{vendor.phone || '—'}</td>
                    <td>
                      {vendor.website ? (
                        <a className="link" href={vendor.website} target="_blank" rel="noreferrer">
                          {vendor.website}
                        </a>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="max-w-xs truncate">{vendor.notes || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
