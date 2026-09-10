import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  apiErrorMessage,
  listDiscoveredProcesses,
  type AgentMessage,
  type ProcessSummary,
} from '../services/apiClient'
import ProcessDiscoveryPanel from '../components/discovery/ProcessDiscoveryPanel'
import {
  Alert,
  Badge,
  EmptyState,
  PageHeader,
  Panel,
  Spinner,
} from '../components/ui/primitives'

export default function DiscoverPage() {
  const navigate = useNavigate()
  const [processes, setProcesses] = useState<ProcessSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const [listing, setListing] = useState(true)
  const [latest, setLatest] = useState<AgentMessage | null>(null)

  async function refreshList() {
    setListing(true)
    try {
      const rows = await listDiscoveredProcesses()
      setProcesses(rows)
      setError(null)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setListing(false)
    }
  }

  useEffect(() => {
    void refreshList()
  }, [])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Process Discovery"
        description="Upload process evidence to extract activities, rules, and dependencies. Prefer starting from a process detail page when continuing the full BPMFlow journey."
      />

      {error ? <Alert tone="error">{error}</Alert> : null}

      <ProcessDiscoveryPanel
        processId=""
        discovery={null}
        latestMessage={latest}
        stage="DRAFT"
        hideStandaloneLink
        onDiscoveryComplete={async (message) => {
          setLatest(message)
          await refreshList()
          if (message.process_id) {
            navigate(`/processes/${message.process_id}`, { replace: true })
          }
        }}
      />

      <Panel title="Discovered processes">
        {listing ? (
          <Spinner label="Loading discoveries…" />
        ) : processes.length === 0 ? (
          <EmptyState
            title="No discoveries yet"
            body="Upload process evidence above to extract a process model."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-base-200 text-xs uppercase text-base-content/55">
                <tr>
                  <th className="px-2 py-2 font-semibold">Name</th>
                  <th className="px-2 py-2 font-semibold">Status</th>
                  <th className="px-2 py-2 font-semibold">Activities</th>
                  <th className="px-2 py-2 font-semibold">Confidence</th>
                  <th className="px-2 py-2 font-semibold">Open</th>
                </tr>
              </thead>
              <tbody>
                {processes.map((p) => (
                  <tr key={p.process_id} className="border-b border-base-200/60">
                    <td className="px-2 py-3 font-medium text-base-content">{p.name}</td>
                    <td className="px-2 py-3">
                      <Badge tone="accent">{p.discovery_status || p.status}</Badge>
                    </td>
                    <td className="px-2 py-3 text-base-content/80">{p.activity_count}</td>
                    <td className="px-2 py-3 text-base-content/80">
                      {p.overall_confidence != null
                        ? `${Math.round(
                            p.overall_confidence <= 1
                              ? p.overall_confidence * 100
                              : p.overall_confidence,
                          )}%`
                        : '—'}
                    </td>
                    <td className="px-2 py-3">
                      <Link
                        to={`/processes/${p.process_id}`}
                        className="text-sm font-medium text-primary hover:underline"
                      >
                        Open process
                      </Link>
                    </td>
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
