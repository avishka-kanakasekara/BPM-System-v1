import { describe, expect, it } from 'vitest'
import { buildCorrelationTimeline } from './correlationTimeline'

describe('buildCorrelationTimeline', () => {
  it('merges audit, advancement, and receipts sorted newest first', () => {
    const events = buildCorrelationTimeline({
      audit: [
        {
          id: 'a1',
          entity_type: 'process',
          entity_id: 'p1',
          action: 'PROCESS_CREATED',
          timestamp: '2026-01-01T10:00:00Z',
        },
      ],
      autonomousActions: [
        {
          stage: 'RISK_REVIEW',
          action: 'risk_review',
          guardrail: 'no auto approval',
          success: true,
          message: 'ok',
          correlation_id: 'corr-123',
          timestamp: '2026-01-01T12:00:00Z',
        },
      ],
      receipts: [
        {
          id: 'r1',
          process_id: 'p1',
          task_id: 't1',
          tool_name: 'create_po_draft',
          action: 'execute',
          attempt_number: 1,
          idempotency_key: 'k1',
          status: 'SUCCESS',
          created_at: '2026-01-01T11:00:00Z',
        },
      ],
      correlationId: 'corr-123',
    })

    expect(events).toHaveLength(3)
    expect(events[0]?.source).toBe('advancement')
    expect(events[1]?.source).toBe('receipt')
    expect(events[2]?.source).toBe('audit')
  })
})
