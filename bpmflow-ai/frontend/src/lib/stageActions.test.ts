import { describe, expect, it } from 'vitest'
import { stageActions } from './stageActions'

describe('stageActions', () => {
  it('disables starting discovery stage without evidence', () => {
    const actions = stageActions({
      stage: 'DRAFT',
      hasDiscovery: false,
      hasTenant: true,
      busy: false,
      humanApprovalPending: false,
    })
    expect(actions[0]?.id).toBe('start_discovery_stage')
    expect(actions[0]?.enabled).toBe(false)
    expect(actions[0]?.reason).toMatch(/discovery/i)
  })

  it('enables directory resource planning during RESOURCE_PLANNING', () => {
    const actions = stageActions({
      stage: 'RESOURCE_PLANNING',
      hasDiscovery: true,
      hasTenant: true,
      busy: false,
      humanApprovalPending: false,
    })
    expect(actions[0]?.id).toBe('plan_resources')
    expect(actions[0]?.enabled).toBe(true)
  })

  it('does not offer unsupervised full-workflow execution', () => {
    const actions = stageActions({
      stage: 'WORKFLOW_EXECUTION',
      hasDiscovery: true,
      hasTenant: true,
      busy: false,
      humanApprovalPending: false,
    })
    expect(actions).toEqual([])
  })
})
