import { FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { listDirectoryApprovers } from '../../services/apiClient'
import type { ApproverCandidate } from '../../types/api'
import { Alert, EmptyState, PageHeader, Panel } from '../../components/ui/primitives'
import { operationsErrorMessage } from '../../lib/operations'

export default function ApprovalAuthoritiesPage() {
  const [approvalType, setApprovalType] = useState('')
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState('')
  const [rows, setRows] = useState<ApproverCandidate[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onLookup(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const data = await listDirectoryApprovers({
        approval_type: approvalType.trim(),
        amount: amount.trim() || undefined,
        currency: currency.trim() || undefined,
      })
      setRows(data)
    } catch (err) {
      setRows(null)
      setError(operationsErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Approval authorities"
        description="Approval authority is used by Agent3 when checking whether a person is eligible for an approval task. This page cannot override authority."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Panel title="Lookup">
        <p className="mb-3 text-sm text-slate-600">
          There is no list-all authorities API. GET /company/approvers requires an approval type.
        </p>
        <form className="grid gap-3 sm:grid-cols-3" onSubmit={(e) => void onLookup(e)}>
          <label className="text-sm">
            Approval type
            <input required className="input input-bordered mt-1 w-full" value={approvalType} onChange={(e) => setApprovalType(e.target.value)} />
          </label>
          <label className="text-sm">
            Amount (optional)
            <input className="input input-bordered mt-1 w-full" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </label>
          <label className="text-sm">
            Currency (optional)
            <input className="input input-bordered mt-1 w-full" value={currency} onChange={(e) => setCurrency(e.target.value)} />
          </label>
          <div>
            <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
              {busy ? 'Looking up…' : 'Look up authorities'}
            </button>
          </div>
        </form>
      </Panel>
      <Panel title="Results">
        {rows == null ? (
          <EmptyState title="No lookup yet" body="Enter an approval type returned by the directory to see eligible approvers." />
        ) : rows.length === 0 ? (
          <EmptyState title="No matching authorities" body="The backend returned no approver candidates for this query." />
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Role</th>
                  <th>Authority</th>
                  <th>Amount</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.employee_id}-${row.approval_type}-${row.authority_code}`}>
                    <td>
                      <Link className="link" to={`/directory/employees/${row.employee_id}`}>
                        {row.full_name}
                      </Link>
                    </td>
                    <td>{row.role_name}</td>
                    <td>{row.authority_code || 'Unavailable'}</td>
                    <td>
                      {row.max_amount} {row.currency}
                    </td>
                    <td>{row.approval_type}</td>
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
