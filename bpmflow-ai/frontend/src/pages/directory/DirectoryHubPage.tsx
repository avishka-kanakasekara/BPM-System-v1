import { Link } from 'react-router-dom'
import { PageHeader, Panel } from '../../components/ui/primitives'

export default function DirectoryHubPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Company Directory"
        description="Persisted tenant employees, departments, roles, and approval eligibility used by Agent 3. The frontend does not decide eligibility."
      />
      <Panel>
        <p className="text-sm text-slate-600">
          Company Directory → Agent 3 eligibility checks → eligible employee/resource → Workflow Step → Agent 4 plan / approval.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Link className="btn btn-outline" to="/directory/employees">
            Employees
          </Link>
          <Link className="btn btn-outline" to="/directory/departments">
            Departments
          </Link>
          <Link className="btn btn-outline" to="/directory/authorities">
            Approval authorities
          </Link>
        </div>
      </Panel>
    </div>
  )
}
