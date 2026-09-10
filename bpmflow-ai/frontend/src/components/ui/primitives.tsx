import type { ReactNode } from 'react'
import {
  STATUS_TONE_CLASSES,
  approvalTone,
  exceptionTone,
  formatApprovalStatus,
  formatExceptionStatus,
  formatProcessStage,
  formatRiskLevel,
  processStageTone,
  riskTone,
  type StatusTone,
} from '../../lib/statusPresentation'

/** Shared form control classes for consistent inputs across pages. */
export const controlClassName =
  'h-10 w-full rounded-lg border border-base-300 bg-base-100 px-3 text-sm text-base-content outline-none transition-colors placeholder:text-base-content/40 focus:border-base-content/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-base-content/30'

export const textareaClassName =
  'w-full rounded-lg border border-base-300 bg-base-100 px-3 py-2.5 text-sm text-base-content outline-none transition-colors placeholder:text-base-content/40 focus:border-base-content/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-base-content/30'

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 max-w-3xl">
        <h2 className="text-2xl font-semibold tracking-tight text-base-content sm:text-[1.75rem]">
          {title}
        </h2>
        {description ? (
          <p className="mt-1.5 text-sm leading-relaxed text-base-content/70 sm:text-[0.95rem]">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function Alert({
  tone = 'info',
  children,
}: {
  tone?: 'info' | 'error' | 'success' | 'warning'
  children: ReactNode
}) {
  const styles = {
    info: 'border-sky-200/80 bg-sky-50 text-sky-950',
    error: 'border-rose-200/80 bg-rose-50 text-rose-950',
    success: 'border-emerald-200/80 bg-emerald-50 text-emerald-950',
    warning: 'border-amber-200/80 bg-amber-50 text-amber-950',
  }[tone]
  return (
    <div className={`mb-4 rounded-lg border px-4 py-3 text-sm ${styles}`} role="status">
      {children}
    </div>
  )
}

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: StatusTone
}) {
  const styles = STATUS_TONE_CLASSES[tone] ?? STATUS_TONE_CLASSES.neutral
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium tracking-wide ${styles}`}
    >
      {children}
    </span>
  )
}

export function ProcessStageBadge({ stage }: { stage: string }) {
  return <Badge tone={processStageTone(stage)}>{formatProcessStage(stage)}</Badge>
}

export function RiskBadge({ level }: { level: string }) {
  return <Badge tone={riskTone(level)}>{formatRiskLevel(level)}</Badge>
}

export function ApprovalStatusBadge({ status }: { status: string }) {
  return <Badge tone={approvalTone(status)}>{formatApprovalStatus(status)}</Badge>
}

export function ExceptionStatusBadge({ status }: { status: string }) {
  return <Badge tone={exceptionTone(status)}>{formatExceptionStatus(status)}</Badge>
}

export function Panel({
  title,
  children,
  actions,
}: {
  title?: string
  children: ReactNode
  actions?: ReactNode
}) {
  return (
    <section className="rounded-xl border border-base-200 bg-base-100 shadow-[0_1px_2px_rgb(15_23_42_/_0.04)]">
      {(title || actions) && (
        <div className="flex items-center justify-between gap-3 border-b border-base-200 px-5 py-3.5">
          {title ? (
            <h3 className="text-sm font-semibold text-base-content">{title}</h3>
          ) : (
            <span />
          )}
          {actions}
        </div>
      )}
      <div className="p-5 sm:p-6">{children}</div>
    </section>
  )
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string
  body: string
  action?: ReactNode
}) {
  return (
    <div className="rounded-xl border border-dashed border-base-300 bg-base-200/40 px-6 py-10 text-center">
      <p className="text-sm font-semibold text-base-content">{title}</p>
      <p className="mx-auto mt-1.5 max-w-md text-sm leading-relaxed text-base-content/70">{body}</p>
      {action ? <div className="mt-5 flex flex-wrap items-center justify-center gap-2">{action}</div> : null}
    </div>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-base-300/70 ${className}`} aria-hidden />
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-base-content/60" role="status">
      <span className="loading loading-spinner loading-sm" aria-hidden />
      <span>{label}</span>
    </div>
  )
}

/** @deprecated Prefer processStageTone / ProcessStageBadge — kept for existing page imports. */
export function stageTone(stage: string): StatusTone {
  return processStageTone(stage)
}

export {
  formatProcessStage,
  formatRiskLevel,
  formatApprovalStatus,
  formatExceptionStatus,
  processStageTone,
} from '../../lib/statusPresentation'
