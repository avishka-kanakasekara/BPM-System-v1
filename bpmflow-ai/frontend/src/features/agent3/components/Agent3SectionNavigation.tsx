import { Link, useLocation } from 'react-router-dom';
import { allocationRequestPath, recommendationLookupPath } from '../navigation/recommendationNavigation';

const links = [{ to: allocationRequestPath, label: 'New Allocation' }, { to: recommendationLookupPath, label: 'Recommendation Lookup' }];
export function Agent3SectionNavigation() {
  const { pathname } = useLocation();
  return <nav aria-label="Agent 3 section navigation" className="flex flex-wrap gap-2 text-sm">{links.map(({ to, label }) => {
    const active = pathname === to;
    return <Link key={to} to={to} aria-current={active ? 'page' : undefined} className={`rounded-md px-3 py-2 font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 ${active ? 'bg-indigo-100 text-indigo-800' : 'text-indigo-700 underline hover:bg-indigo-50'}`}>{label}{active && <span className="sr-only"> (current page)</span>}</Link>;
  })}</nav>;
}
