import { Link } from 'react-router-dom'
import { Alert, PageHeader, Panel } from '../../components/ui/primitives'

/**
 * Isolated from primary navigation. Free-form POST /agent2/execute is not the product flow.
 */
export default function Agent2ToolsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Agent 2 tools (isolated)"
        description="Agent 2 executes one authorized Workflow Step using an allow-listed registered tool. Capability listing remains on GET /api/v1/agent2/tools."
      />
      <Alert tone="warning">
        One request → one Workflow Step → one registered tool → one receipt. This page is not a free-form RPA launcher
        and does not offer a tool dropdown for execution. Use the Process Cockpit Execute step action.
      </Alert>
      <Panel>
        <p className="text-sm text-slate-600">
          Registered tools live in the Tool Registry. Arbitrary tool execution is not offered here.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link to="/tools" className="btn btn-primary btn-sm">
            Tool Registry
          </Link>
          <Link to="/agent2" className="btn btn-ghost btn-sm">
            Execution telemetry
          </Link>
          <Link to="/agent2/receipts" className="btn btn-ghost btn-sm">
            Receipts
          </Link>
        </div>
      </Panel>
    </div>
  )
}
