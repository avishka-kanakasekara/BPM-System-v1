import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getEmployee, listCompanyRoles, listDepartments, listEmployees } from '../../services/apiClient'
import type { DepartmentRecord, EmployeeRecord, RoleRecord } from '../../types/api'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import { operationsErrorMessage } from '../../lib/operations'
import { formatPct, unavailable } from '../../lib/directoryDisplay'

export default function EmployeeDetailPage() {
  const { employeeId = '' } = useParams()
  const [row, setRow] = useState<EmployeeRecord | null>(null)
  const [manager, setManager] = useState<EmployeeRecord | null>(null)
  const [department, setDepartment] = useState<DepartmentRecord | null>(null)
  const [role, setRole] = useState<RoleRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!employeeId) return
    setLoading(true)
    setError(null)
    try {
      const employee = await getEmployee(employeeId)
      setRow(employee)
      const [deps, roles, staff] = await Promise.all([
        listDepartments().catch(() => [] as DepartmentRecord[]),
        listCompanyRoles().catch(() => [] as RoleRecord[]),
        employee.manager_employee_id ? listEmployees().catch(() => [] as EmployeeRecord[]) : Promise.resolve([] as EmployeeRecord[]),
      ])
      setDepartment(deps.find((d) => d.department_id === employee.department_id) ?? null)
      setRole(roles.find((r) => r.role_id === employee.role_id) ?? null)
      setManager(staff.find((e) => e.employee_id === employee.manager_employee_id) ?? null)
    } catch (err) {
      setRow(null)
      setError(operationsErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [employeeId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  if (loading && !row) {
    return (
      <div aria-busy="true">
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  if (!row) {
    return (
      <div className="space-y-4">
        <Link to="/directory/employees" className="text-sm font-medium text-slate-500">
          ← Employees
        </Link>
        {error ? <Alert tone="error">{error}</Alert> : <EmptyState title="Employee not found" body="No directory record was returned." />}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Link to="/directory/employees" className="text-sm font-medium text-slate-500">
        ← Employees
      </Link>
      <PageHeader title={row.full_name} description={row.employee_number} />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Panel title="Company Directory identity">
        <p className="mb-4 text-sm text-slate-600">
          Agent3 uses Company Directory data to resolve eligible employees/resources for workflow tasks and approvals. This
          page does not control Agent 3 decisions.
        </p>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase text-slate-500">Verified email</dt>
            <dd>{row.email}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Phone</dt>
            <dd>{unavailable(row.phone)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Department</dt>
            <dd>
              {department ? (
                <Link className="link" to={`/directory/departments`}>
                  {department.name}
                </Link>
              ) : (
                'Unavailable'
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Role</dt>
            <dd>{role?.name || 'Unavailable'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Manager</dt>
            <dd>
              {row.manager_employee_id ? (
                <Link className="link" to={`/directory/employees/${row.manager_employee_id}`}>
                  {manager?.full_name || row.manager_employee_id}
                </Link>
              ) : (
                'Unavailable'
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Status</dt>
            <dd>{row.status}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Availability</dt>
            <dd>{row.is_available == null ? 'Unavailable' : row.is_available ? 'Available' : 'Not available'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Current workload</dt>
            <dd>{formatPct(row.current_workload_pct)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Max workload</dt>
            <dd>{formatPct(row.max_workload_pct)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Skills</dt>
            <dd>{row.skill_codes?.length ? row.skill_codes.join(', ') : 'Unavailable'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Approval authority</dt>
            <dd>
              Not returned on the employee record.{' '}
              <Link className="link" to="/directory/authorities">
                Look up authorities
              </Link>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Linked resource ID</dt>
            <dd className="break-all font-mono text-xs">{unavailable(row.resource_id)}</dd>
          </div>
        </dl>
      </Panel>
    </div>
  )
}
