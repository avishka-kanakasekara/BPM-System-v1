import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listDepartments, listEmployees } from '../../services/apiClient'
import type { DepartmentRecord, EmployeeRecord } from '../../types/api'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import { operationsErrorMessage } from '../../lib/operations'

export default function DepartmentsPage() {
  const [rows, setRows] = useState<DepartmentRecord[]>([])
  const [employees, setEmployees] = useState<EmployeeRecord[]>([])
  const [openId, setOpenId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const counts = useMemo(() => {
    const map = new Map<string, number>()
    for (const e of employees) {
      map.set(e.department_id, (map.get(e.department_id) || 0) + 1)
    }
    return map
  }, [employees])

  const staffByDept = useMemo(() => {
    const map = new Map<string, EmployeeRecord[]>()
    for (const e of employees) {
      const list = map.get(e.department_id) || []
      list.push(e)
      map.set(e.department_id, list)
    }
    return map
  }, [employees])

  const employeeName = useMemo(() => {
    const map = new Map(employees.map((e) => [e.employee_id, e.full_name]))
    return (id: string | null | undefined) => (id ? map.get(id) : undefined)
  }, [employees])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [deps, staff] = await Promise.all([listDepartments(), listEmployees().catch(() => [] as EmployeeRecord[])])
      setRows(deps)
      setEmployees(staff)
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

  return (
    <div className="space-y-6">
      <PageHeader
        title="Departments"
        description="Persisted company departments. Employee membership uses department_id from directory records."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Panel>
        {loading ? (
          <div aria-busy="true">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState title="No departments" body="No department records were returned." />
        ) : (
          <ul className="space-y-3">
            {rows.map((dept) => (
              <li key={dept.department_id} className="rounded-lg border border-slate-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{dept.name}</p>
                    <p className="text-sm text-slate-500">Code {dept.code}</p>
                  </div>
                  <span className="text-sm">{dept.status || 'Unavailable'}</span>
                </div>
                <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Manager</dt>
                    <dd>
                      {dept.manager_employee_id ? (
                        <Link className="link" to={`/directory/employees/${dept.manager_employee_id}`}>
                          {employeeName(dept.manager_employee_id) || dept.manager_employee_id}
                        </Link>
                      ) : (
                        'Unavailable'
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Employees (from directory)</dt>
                    <dd>{counts.get(dept.department_id) ?? 0}</dd>
                  </div>
                </dl>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm mt-2"
                  onClick={() => setOpenId((id) => (id === dept.department_id ? null : dept.department_id))}
                >
                  {openId === dept.department_id ? 'Hide employees' : 'Show employees'}
                </button>
                {openId === dept.department_id ? (
                  <ul className="mt-2 space-y-1 text-sm">
                    {(staffByDept.get(dept.department_id) || []).map((e) => (
                      <li key={e.employee_id}>
                        <Link className="link" to={`/directory/employees/${e.employee_id}`}>
                          {e.full_name}
                        </Link>
                      </li>
                    ))}
                    {(staffByDept.get(dept.department_id) || []).length === 0 ? (
                      <li className="text-slate-500">No employees linked by department_id.</li>
                    ) : null}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  )
}
