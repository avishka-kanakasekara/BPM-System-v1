import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import RequesterView from './pages/RequesterView'
import TaskView from './pages/TaskView'
import ApprovalView from './pages/ApprovalView'
import ExceptionView from './pages/ExceptionView'
import AuditTraceView from './pages/AuditTraceView'
import AllocationRequestPage from './features/agent3/pages/AllocationRequestPage'
import RecommendationResultPage from './features/agent3/pages/RecommendationResultPage'
import RecommendationLookupPage from './features/agent3/pages/RecommendationLookupPage'
import { Agent3ErrorBoundary } from './features/agent3/components/Agent3ErrorBoundary'

function App() {
  return (
    <Router>
      <div className="min-h-screen">
        <Routes>
          <Route path="/" element={<RequesterView />} />
          <Route path="/tasks" element={<TaskView />} />
          <Route path="/approvals" element={<ApprovalView />} />
          <Route path="/exceptions" element={<ExceptionView />} />
          <Route path="/audit" element={<AuditTraceView />} />
          <Route path="/agent3/allocations/new" element={<Agent3ErrorBoundary><AllocationRequestPage /></Agent3ErrorBoundary>} />
          <Route path="/agent3/recommendations/lookup" element={<Agent3ErrorBoundary><RecommendationLookupPage /></Agent3ErrorBoundary>} />
          <Route path="/agent3/recommendations/:recommendationId" element={<Agent3ErrorBoundary><RecommendationResultPage /></Agent3ErrorBoundary>} />
        </Routes>
      </div>
    </Router>
  )
}

export default App
