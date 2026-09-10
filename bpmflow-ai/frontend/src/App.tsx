import { BrowserRouter, Navigate, Outlet, Route, Routes, useParams } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import AppShell from './components/layout/AppShell'
import { RequireAuth } from './components/RequireAuth'
import DashboardPage from './pages/DashboardPage'
import DiscoverPage from './pages/DiscoverPage'
import ProcessesPage from './pages/ProcessesPage'
import CreateProcessPage from './pages/CreateProcessPage'
import ProcessDetailPage from './pages/ProcessDetailPage'
import ApprovalsPage from './pages/ApprovalsPage'
import ApprovalDetailPage from './pages/ApprovalDetailPage'
import ExceptionsPage from './pages/ExceptionsPage'
import ExceptionDetailPage from './pages/ExceptionDetailPage'
import AuditPage from './pages/AuditPage'
import SignInPage from './pages/SignInPage'
import SignUpPage from './pages/SignUpPage'
import TasksPage from './pages/TasksPage'
import SettingsPage from './pages/SettingsPage'
import Agent2KpisPage from './pages/agent2/KpisPage'
import Agent2ReceiptsPage from './pages/agent2/ReceiptsPage'
import Agent2RecommendationsPage from './pages/agent2/RecommendationsPage'
import AllocationRequestPage from './features/agent3/pages/AllocationRequestPage'
import RecommendationResultPage from './features/agent3/pages/RecommendationResultPage'
import RecommendationLookupPage from './features/agent3/pages/RecommendationLookupPage'
import { Agent3ErrorBoundary } from './features/agent3/components/Agent3ErrorBoundary'

/** Preserve /workflows/:processId deep links by aliasing to /processes/:processId */
function WorkflowProcessRedirect() {
  const { processId } = useParams()
  return <Navigate to={`/processes/${processId}`} replace />
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="sign-in" element={<SignInPage />} />
            <Route path="sign-up" element={<SignUpPage />} />

            <Route
              element={
                <RequireAuth>
                  <Outlet />
                </RequireAuth>
              }
            >
              <Route index element={<DashboardPage />} />
              <Route path="processes" element={<ProcessesPage />} />
              <Route path="processes/new" element={<CreateProcessPage />} />
              <Route path="processes/:processId" element={<ProcessDetailPage />} />
              <Route path="workflows" element={<Navigate to="/processes" replace />} />
              <Route path="workflows/:processId" element={<WorkflowProcessRedirect />} />
              <Route path="tasks" element={<TasksPage />} />
              <Route path="approvals" element={<ApprovalsPage />} />
              <Route path="approvals/:approvalId" element={<ApprovalDetailPage />} />
              <Route path="exceptions" element={<ExceptionsPage />} />
              <Route path="exceptions/:exceptionId" element={<ExceptionDetailPage />} />
              <Route path="audit" element={<AuditPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="discover" element={<DiscoverPage />} />
              <Route path="agent2/kpis" element={<Agent2KpisPage />} />
              <Route path="agent2/receipts" element={<Agent2ReceiptsPage />} />
              <Route path="agent2/recommendations" element={<Agent2RecommendationsPage />} />
              <Route
                path="agent3/allocations/new"
                element={
                  <Agent3ErrorBoundary>
                    <AllocationRequestPage />
                  </Agent3ErrorBoundary>
                }
              />
              <Route
                path="agent3/recommendations/lookup"
                element={
                  <Agent3ErrorBoundary>
                    <RecommendationLookupPage />
                  </Agent3ErrorBoundary>
                }
              />
              <Route
                path="agent3/recommendations/:recommendationId"
                element={
                  <Agent3ErrorBoundary>
                    <RecommendationResultPage />
                  </Agent3ErrorBoundary>
                }
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
