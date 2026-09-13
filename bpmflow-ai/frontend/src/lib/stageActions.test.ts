import { describe, expect, it } from 'vitest'
import { stageActions } from './stageActions'

describe('stageActions', () => {
  it('disables autopilot without discovery evidence', () => {
    const actions = stageActions({
      stage: 'DRAFT',
      hasDiscovery: false,
      hasTenant: true,
      busy: false,
      humanApprovalPending: false,
    })
    expect(actions[0]?.enabled).toBe(false)
    expect(actions[0]?.reason).toMatch(/discovery/i)
  })

  it('enables continue autopilot during resource planning', () => {
    const actions = stageActions({
      stage: 'RESOURCE_PLANNING',
      hasDiscovery: true,
      hasTenant: true,
      busy: false,
      humanApprovalPending: false,
    })
    expect(actions[0]?.id).toBe('continue_autopilot')
    expect(actions[0]?.enabled).toBe(true)
  })
})
