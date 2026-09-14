import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { createEmployee, listCompanyRoles, listDepartments, listEmployees } from '../../services/apiClient'
import type { DepartmentRecord, EmployeeRecord, RoleRecord } from '../../types/api'
import { useAuth } from '../../auth/AuthContext'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import { operationsErrorMessage } from '../../lib/operations'
import { formatPct } from '../../lib/directoryDisplay'

export default function EmployeesPage() {
  const { user } = useAuth()
  const isAdmin = (user?.role || '').toLowerCase() === 'admin'
  const [params] = useSearchParams()
  const departmentFilter = params.get('department') || ''
  const [rows, setRows] = useState<EmployeeRecord[]>([])
  const [departments, setDepartments] = useState<DepartmentRecord[]>([])
  const [roles, setRoles] = useState<RoleRecord[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [number, setNumber] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [departmentId, setDepartmentId] = useState('')
  const [roleId, setRoleId] = useState('')

  const deptName = useMemo(() => {
    const map = new Map(departments.map((d) => [d.department_id, d.name]))
    return (id: string) => map.get(id) ?? 'Unavailable'
  }, [departments])
  const roleName = useMemo(() => {
    const map = new Map(roles.map((r) => [r.role_id, r.name]))
    return (id: string) => map.get(id) ?? 'Unavailable'
  }, [roles])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [employees, deps, roleRows] = await Promise.all([
        listEmployees(),
        listDepartments().catch(() => [] as DepartmentRecord[]),
        listCompanyRoles().catch(() => [] as RoleRecord[]),
      ])
      setRows(employees)
      setDepartments(deps)
      setRoles(roleRows)
    } catch (err) {
      setError(operationsErrorMessage(err))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const filtered = rows.filter((row) => {
    if (departmentFilter && row.department_id !== departmentFilter) return false
    const hay = `${row.full_name} ${row.employee_number} ${row.email}`.toLowerCase()
    return hay.includes(query.trim().toLowerCase())
  })

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
      await createEmployee({
        tenant_id: user.tenant_id,
        employee_number: number.trim(),
        full_name: name.trim(),
        email: email.trim(),
        department_id: departmentId,
        role_id: roleId,
      })
      setNumber('')
      setName('')
      setEmail('')
      setNotice('Employee created in the company directory.')
      await refresh()
    } catch (err) {
      setError(operationsErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Employees"
        description="Company Directory identities used by Agent 3. Eligibility is decided on the backend."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice ? <Alert tone="success">{notice}</Alert> : null}

      {isAdmin ? (
        <Panel title="Add employee (admin)">
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => void onCreate(e)}>
            <label className="text-sm">
              Employee number
              <input required className="input input-bordered mt-1 w-full" value={number} onChange={(e) => setNumber(e.target.value)} />
            </label>
            <label className="text-sm">
              Full name
              <input required className="input input-bordered mt-1 w-full" value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="text-sm">
              Verified email
              <input required type="email" className="input input-bordered mt-1 w-full" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label className="text-sm">
              Department
              <select required className="select select-bordered mt-1 w-full" value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
                <option value="">Select department</option>
                {departments.map((d) => (
                  <option key={d.department_id} value={d.department_id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              Role
              <select required className="select select-bordered mt-1 w-full" value={roleId} onChange={(e) => setRoleId(e.target.value)}>
                <option value="">Select role</option>
                {roles.map((r) => (
                  <option key={r.role_id} value={r.role_id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="sm:col-span-2">
              <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
                {busy ? 'Saving…' : 'Create employee'}
              </button>
            </div>
          </form>
        </Panel>
      ) : null}

      <Panel title="Directory">
        <input
          className="input input-bordered mb-4 w-full max-w-md"
          placeholder="Search name, number, or email"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {loading ? (
          <div aria-busy="true">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState title="No employees" body="No company directory employees were returned for this filter." />
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Number</th>
                  <th>Email</th>
                  <th>Department</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Skills</th>
                  <th>Approval authority</th>
                  <th>Availability</th>
                  <th>Workload</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr key={row.employee_id}>
                    <td>
                      <Link className="link font-medium" to={`/directory/employees/${row.employee_id}`}>
                        {row.full_name}
                      </Link>
                    </td>
                    <td>{row.employee_number}</td>
                    <td>{row.email}</td>
                    <td>{deptName(row.department_id)}</td>
                    <td>{roleName(row.role_id)}</td>
                    <td>{row.status}</td>
                    <td>{row.skill_codes?.length ? row.skill_codes.join(', ') : 'Unavailable'}</td>
                    <td>Unavailable</td>
                    <td>{row.is_available == null ? 'Unavailable' : row.is_available ? 'Available' : 'Not available'}</td>
                    <td>{formatPct(row.current_workload_pct)}</td>
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
