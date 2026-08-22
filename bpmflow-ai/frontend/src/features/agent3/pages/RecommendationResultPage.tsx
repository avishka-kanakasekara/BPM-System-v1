import { useEffect, useRef, useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { getRecommendationById } from '../api/agent3Api';
import type { Agent3ClientError } from '../api/normalizeAgent3Error';
import { FullRecommendation, RecommendationErrorState, RecommendationLoadingState, SummaryRecommendation } from '../components/RecommendationPresentation';
import { Agent3SectionNavigation } from '../components/Agent3SectionNavigation';
import { getRecommendationNavigationResponse } from '../navigation/recommendationNavigation';
import type { RecommendationSummary } from '../types/agent3Api';
import { isValidUUID } from '../utils/metadata';

function safeError(error: unknown): { title: string; message: string } {
  const value = error as Partial<Agent3ClientError>;
  if (value.kind === 'authentication') return { title: 'Authentication required', message: 'Your session is unavailable or expired. Sign in before retrieving this recommendation.' };
  if (value.kind === 'authorization') return { title: 'Access unavailable', message: 'You are not authorized to view this recommendation.' };
  if (value.kind === 'not_found') return { title: 'Recommendation unavailable', message: 'The recommendation was not found or is not available to this tenant.' };
  if (value.kind === 'unavailable') return { title: 'Service unavailable', message: 'The recommendation service is temporarily unavailable.' };
  return { title: 'Recommendation unavailable', message: 'The recommendation could not be loaded safely.' };
}

export default function RecommendationResultPage() {
  const { recommendationId = '' } = useParams(); const location = useLocation();
  const full = getRecommendationNavigationResponse(location.state, recommendationId);
  const generation = useRef(0);
  const [state, setState] = useState<{ kind: 'loading' } | { kind: 'summary'; value: RecommendationSummary } | { kind: 'error'; title: string; message: string }>({ kind: 'loading' });

  useEffect(() => {
    if (full) return;
    if (!isValidUUID(recommendationId)) { setState({ kind: 'error', title: 'Invalid recommendation ID', message: 'Enter or open a valid recommendation UUID.' }); return; }
    const request = ++generation.current; let active = true; setState({ kind: 'loading' });
    getRecommendationById(recommendationId).then((value) => { if (active && request === generation.current) setState(value.recommendation_id === recommendationId ? { kind: 'summary', value } : { kind: 'error', title: 'Recommendation unavailable', message: 'The returned recommendation did not match the requested identifier.' }); }).catch((error) => { if (active && request === generation.current) setState({ kind: 'error', ...safeError(error) }); });
    return () => { active = false; };
  }, [full, recommendationId]);

  let content;
  if (full) content = <FullRecommendation response={full} />;
  else if (state.kind === 'loading') content = <RecommendationLoadingState />;
  else if (state.kind === 'summary') content = <SummaryRecommendation summary={state.value} />;
  else content = <RecommendationErrorState title={state.title} message={state.message} />;
  return <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-900"><div className="mx-auto max-w-6xl space-y-6"><Agent3SectionNavigation />{content}</div></main>;
}
