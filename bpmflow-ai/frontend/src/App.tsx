import { BrowserRouter, Navigate, Outlet, Route, Routes, useParams } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import AppShell from './components/layout/AppShell'
import { RequireAuth } from './components/RequireAuth'
import { RequireRole } from './components/RequireRole'
import DashboardPage from './pages/DashboardPage'
import DiscoverPage from './pages/DiscoverPage'
import ProcessesPage from './pages/ProcessesPage'
import CreateProcessPage from './pages/CreateProcessPage'
import ProcessDetailPage from './pages/ProcessDetailPage'
import ApprovalsPage from './pages/ApprovalsPage'
import ApprovalDetailPage from './pages/ApprovalDetailPage'
import AuditPage from './pages/AuditPage'
import PoliciesPage from './pages/PoliciesPage'
import SignInPage from './pages/SignInPage'
import SignUpPage from './pages/SignUpPage'
import TasksPage from './pages/TasksPage'
import SettingsPage from './pages/SettingsPage'
import Agent2DashboardPage from './pages/agent2/DashboardPage'
import Agent2ExecutionDetailPage from './pages/agent2/ExecutionDetailPage'
import Agent2KpisPage from './pages/agent2/KpisPage'
import Agent2ReceiptsPage from './pages/agent2/ReceiptsPage'
import Agent2RecommendationsPage from './pages/agent2/RecommendationsPage'
import Agent2ToolsPage from './pages/agent2/ToolsPage'
import ExceptionsPage from './pages/ExceptionsPage'
import ExceptionDetailPage from './pages/ExceptionDetailPage'
import MonitoringHubPage from './pages/MonitoringHubPage'
import ProcessMonitoringPage from './pages/ProcessMonitoringPage'
import TobeRecommendationsPage from './pages/TobeRecommendationsPage'
import TobeRecommendationDetailPage from './pages/TobeRecommendationDetailPage'
import VendorsPage from './pages/procurement/VendorsPage'
import VendorDetailPage from './pages/procurement/VendorDetailPage'
import QuotationsPage from './pages/procurement/QuotationsPage'
import PurchaseOrdersPage from './pages/procurement/PurchaseOrdersPage'
import PurchaseOrderDetailPage from './pages/procurement/PurchaseOrderDetailPage'
import InvoicesPage from './pages/procurement/InvoicesPage'
import InvoiceDetailPage from './pages/procurement/InvoiceDetailPage'
import { Agent3ErrorBoundary } from './features/agent3/components/Agent3ErrorBoundary'
import AllocationRequestPage from './features/agent3/pages/AllocationRequestPage'
import RecommendationResultPage from './features/agent3/pages/RecommendationResultPage'
import RecommendationLookupPage from './features/agent3/pages/RecommendationLookupPage'
import DirectoryHubPage from './pages/directory/DirectoryHubPage'
import EmployeesPage from './pages/directory/EmployeesPage'
import EmployeeDetailPage from './pages/directory/EmployeeDetailPage'
import DepartmentsPage from './pages/directory/DepartmentsPage'
import ApprovalAuthoritiesPage from './pages/directory/ApprovalAuthoritiesPage'
import ToolsPage from './pages/tools/ToolsPage'
import ToolDetailPage from './pages/tools/ToolDetailPage'
import SystemHealthPage from './pages/admin/SystemHealthPage'

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
              <Route path="processes/:processId/monitoring" element={<ProcessMonitoringPage />} />
              <Route path="processes/:processId" element={<ProcessDetailPage />} />
              <Route path="workflows" element={<Navigate to="/processes" replace />} />
              <Route path="workflows/:processId" element={<WorkflowProcessRedirect />} />
              <Route
                path="tasks"
                element={
                  <RequireRole roles={['requester', 'admin']}>
                    <TasksPage />
                  </RequireRole>
                }
              />
              <Route
                path="approvals"
                element={
                  <RequireRole roles={['approver', 'admin']}>
                    <ApprovalsPage />
                  </RequireRole>
                }
              />
              <Route
                path="approvals/:approvalId"
                element={
                  <RequireRole roles={['approver', 'admin']}>
                    <ApprovalDetailPage />
                  </RequireRole>
                }
              />
              <Route path="exceptions" element={<ExceptionsPage />} />
              <Route path="exceptions/:exceptionId" element={<ExceptionDetailPage />} />
              <Route path="monitoring" element={<MonitoringHubPage />} />
              <Route path="recommendations" element={<TobeRecommendationsPage />} />
              <Route path="recommendations/:recommendationId" element={<TobeRecommendationDetailPage />} />
              <Route path="vendors" element={<VendorsPage />} />
              <Route path="vendors/:vendorId" element={<VendorDetailPage />} />
              <Route path="quotations" element={<QuotationsPage />} />
              <Route path="purchase-orders" element={<PurchaseOrdersPage />} />
              <Route path="purchase-orders/:processId" element={<PurchaseOrderDetailPage />} />
              <Route path="invoices" element={<InvoicesPage />} />
              <Route path="invoices/:invoiceId" element={<InvoiceDetailPage />} />
              <Route path="directory" element={<DirectoryHubPage />} />
              <Route path="directory/employees" element={<EmployeesPage />} />
              <Route path="directory/employees/:employeeId" element={<EmployeeDetailPage />} />
              <Route path="directory/departments" element={<DepartmentsPage />} />
              <Route path="directory/authorities" element={<ApprovalAuthoritiesPage />} />
              <Route path="tools" element={<ToolsPage />} />
              <Route path="tools/:toolId" element={<ToolDetailPage />} />
              <Route
                path="admin/system"
                element={
                  <RequireRole roles={['admin']}>
                    <SystemHealthPage />
                  </RequireRole>
                }
              />
              <Route path="audit" element={<AuditPage />} />
              <Route
                path="policies"
                element={
                  <RequireRole roles={['admin']}>
                    <PoliciesPage />
                  </RequireRole>
                }
              />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="discover" element={<DiscoverPage />} />
              <Route path="discovery" element={<Navigate to="/discover" replace />} />
              <Route path="agent2" element={<Agent2DashboardPage />} />
              <Route path="agent2/tools" element={<Agent2ToolsPage />} />
              <Route path="agent2/executions/:receiptId" element={<Agent2ExecutionDetailPage />} />
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
