import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { allocationRequestPath, recommendationLookupPath } from '../navigation/recommendationNavigation';

export class Agent3ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(_error: Error, _info: ErrorInfo) { /* Intentionally do not log potentially sensitive render errors. */ }
  render() {
    if (!this.state.failed) return this.props.children;
    return <main className="min-h-screen bg-slate-50 px-4 py-8"><section role="alert" className="mx-auto max-w-3xl rounded-xl border border-red-200 bg-white p-6"><h1 className="text-2xl font-bold text-slate-900">Agent 3 is temporarily unavailable</h1><p className="mt-2 text-slate-600">An unexpected presentation error occurred. No allocation request was retried.</p><nav aria-label="Agent 3 recovery navigation" className="mt-5 flex flex-wrap gap-3"><Link className="rounded-md bg-indigo-600 px-4 py-2 font-medium text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2" to={allocationRequestPath}>New Allocation</Link><Link className="rounded-md border border-indigo-600 px-4 py-2 font-medium text-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2" to={recommendationLookupPath}>Recommendation Lookup</Link></nav></section></main>;
  }
}
