import { Alert, Panel } from '../ui/primitives'
import {
  PROCESS_JOURNEY_STAGES,
  PROCESS_STAGE_DESCRIPTIONS,
  PROCESS_STAGE_TIMELINE_LABELS,
  type WorkflowStage,
} from '../../lib/processStages'

export default function ProcessStageTimeline({ stage }: { stage: string }) {
  const isException = stage === 'EXCEPTION'
  const currentIdx = PROCESS_JOURNEY_STAGES.findIndex((s) => s === stage)

  return (
    <Panel
      title="Process stages"
      actions={
        isException ? (
          <span className="text-xs font-medium text-rose-700">Exception</span>
        ) : null
      }
    >
      {isException ? (
        <Alert tone="warning">{PROCESS_STAGE_DESCRIPTIONS.EXCEPTION}</Alert>
      ) : null}

      <ol className="hidden items-start justify-between gap-1 md:flex">
        {PROCESS_JOURNEY_STAGES.map((key, idx) => {
          const done = !isException && currentIdx > idx
          const current = !isException && currentIdx === idx
          return (
            <li key={key} className="flex min-w-0 flex-1 flex-col items-center text-center">
              <span
                className={[
                  'flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold',
                  done
                    ? 'bg-slate-900 text-white'
                    : current
                      ? 'bg-sky-600 text-white ring-4 ring-sky-100'
                      : 'bg-slate-100 text-slate-400',
                ].join(' ')}
                aria-current={current ? 'step' : undefined}
              >
                {done ? '✓' : current ? '●' : idx + 1}
              </span>
              <span
                className={[
                  'mt-2 text-[11px] font-medium leading-tight',
                  current ? 'text-slate-900' : done ? 'text-slate-700' : 'text-slate-400',
                ].join(' ')}
              >
                {PROCESS_STAGE_TIMELINE_LABELS[key]}
              </span>
            </li>
          )
        })}
      </ol>

      <ol className="space-y-0 md:hidden">
        {PROCESS_JOURNEY_STAGES.map((key: WorkflowStage, idx) => {
          const done = !isException && currentIdx > idx
          const current = !isException && currentIdx === idx
          return (
            <li key={key} className="flex gap-3">
              <div className="flex w-8 flex-col items-center">
                <span
                  className={[
                    'flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold',
                    done
                      ? 'bg-slate-900 text-white'
                      : current
                        ? 'bg-sky-600 text-white'
                        : 'bg-slate-100 text-slate-400',
                  ].join(' ')}
                >
                  {done ? '✓' : current ? '●' : idx + 1}
                </span>
                {idx < PROCESS_JOURNEY_STAGES.length - 1 ? (
                  <span className="my-1 w-px flex-1 bg-slate-200" aria-hidden />
                ) : null}
              </div>
              <div className={idx < PROCESS_JOURNEY_STAGES.length - 1 ? 'pb-4 pt-1.5' : 'pt-1.5'}>
                <p
                  className={[
                    'text-sm font-medium',
                    current ? 'text-slate-900' : done ? 'text-slate-700' : 'text-slate-400',
                  ].join(' ')}
                >
                  {PROCESS_STAGE_TIMELINE_LABELS[key]}
                </p>
              </div>
            </li>
          )
        })}
      </ol>
    </Panel>
  )
}
