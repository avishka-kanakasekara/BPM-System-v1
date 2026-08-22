import { BrowserRouter as Router, Link, Routes, Route } from 'react-router-dom'
import RequesterView from './pages/RequesterView'
import TaskView from './pages/TaskView'
import ApprovalView from './pages/ApprovalView'
import ExceptionView from './pages/ExceptionView'
import AuditTraceView from './pages/AuditTraceView'

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-100">
        <nav className="border-b border-gray-200 bg-white px-8 py-3">
          <div className="mx-auto flex max-w-5xl gap-6 text-sm font-medium text-gray-700">
            <Link className="hover:text-indigo-700" to="/">
              Discover
            </Link>
            <Link className="hover:text-indigo-700" to="/tasks">
              Workflows
            </Link>
            <Link className="hover:text-indigo-700" to="/approvals">
              Approvals
            </Link>
            <Link className="hover:text-indigo-700" to="/exceptions">
              Exceptions
            </Link>
            <Link className="hover:text-indigo-700" to="/audit">
              Audit
            </Link>
          </div>
        </nav>
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
