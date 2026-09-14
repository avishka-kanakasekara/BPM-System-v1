import { describe, expect, it } from 'vitest'
import { isStepExecutableInUi } from './helpers'
import type { WorkflowStepRecord } from '../../types/api'

function step(overrides: Partial<WorkflowStepRecord> = {}): WorkflowStepRecord {
  return {
    id: 'step-1',
    tenant_id: 't1',
    workflow_plan_id: 'plan-1',
    step_key: 'create_po',
    sequence: 5,
    name: 'Create Purchase Order',
    step_type: 'SYSTEM_ACTION',
    status: 'READY',
    ...overrides,
  }
}

describe('isStepExecutableInUi', () => {
  it('allows one-step execution only in WORKFLOW_EXECUTION on an ACTIVE plan', () => {
    expect(
      isStepExecutableInUi({
        processStage: 'WORKFLOW_EXECUTION',
        planStatus: 'ACTIVE',
        step: step(),
      }),
    ).toBe(true)
    expect(
      isStepExecutableInUi({
        processStage: 'WORKFLOW_EXECUTION',
        planStatus: 'DRAFT',
        step: step(),
      }),
    ).toBe(false)
    expect(
      isStepExecutableInUi({
        processStage: 'COMPLETED',
        planStatus: 'ACTIVE',
        step: step(),
      }),
    ).toBe(false)
  })

  it('does not treat approval-waiting steps as executable', () => {
    expect(
      isStepExecutableInUi({
        processStage: 'WORKFLOW_EXECUTION',
        planStatus: 'ACTIVE',
        step: step({ step_type: 'APPROVAL', status: 'AUTHORIZED' }),
      }),
    ).toBe(false)
  })
})
