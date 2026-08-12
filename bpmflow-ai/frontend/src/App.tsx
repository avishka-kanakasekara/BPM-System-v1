import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import RequesterView from './pages/RequesterView'
import TaskView from './pages/TaskView'
import ApprovalView from './pages/ApprovalView'
import ExceptionView from './pages/ExceptionView'
import AuditTraceView from './pages/AuditTraceView'

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-100">
        <Routes>
          <Route path="/" element={<RequesterView />} />
          <Route path="/tasks" element={<TaskView />} />
          <Route path="/approvals" element={<ApprovalView />} />
          <Route path="/exceptions" element={<ExceptionView />} />
          <Route path="/audit" element={<AuditTraceView />} />
        </Routes>
      </div>
    </Router>
  )
}

export default App
