import { describe, expect, it } from 'vitest'
import { mockPersistedAllocationResponse } from '../../features/agent3/tests/fixtures/agent3Contracts'
import { parseProcessAgent3Allocation } from './parseProcessAgent3Allocation'

describe('parseProcessAgent3Allocation', () => {
  it('accepts a strict Agent 3 persisted response', () => {
    const parsed = parseProcessAgent3Allocation(mockPersistedAllocationResponse)
    expect(parsed?.recommendation_id).toBe(mockPersistedAllocationResponse.recommendation_id)
    expect(parsed?.recommendation.status).toBe(mockPersistedAllocationResponse.recommendation.status)
  })

  it('reads nested agent3_allocation metadata', () => {
    const parsed = parseProcessAgent3Allocation({
      agent3_allocation: mockPersistedAllocationResponse,
    })
    expect(parsed?.recommendation_id).toBe(mockPersistedAllocationResponse.recommendation_id)
  })

  it('coerces numeric decimals from workflow JSON', () => {
    const withNumbers = structuredClone(mockPersistedAllocationResponse)
    withNumbers.recommendation.human_requirement_result = {
      resource_type: 'HUMAN',
      eligible_candidates: [
        {
          resource_id: '00000000-0000-0000-0000-000000000021',
          resource_type: 'HUMAN',
          name: 'Candidate',
          rank: 1,
          allocation_score: '0.90',
          score_breakdown: {
            role_match: '0.9',
            skill_match: '0.9',
            availability_score: '0.9',
            workload_fit: '0.9',
            authority_match: '0.9',
            total_score: '0.9',
          },
          current_workload_percentage: '10.0',
          projected_workload_percentage: '20.0',
          available_from: '2026-01-01T00:00:00Z',
          available_until: null,
          evidence_refs: {},
        },
      ],
      excluded_resources: [],
      budget_validation: null,
    }
    const candidate = withNumbers.recommendation.human_requirement_result.eligible_candidates[0]
    ;(candidate as unknown as { allocation_score: number }).allocation_score = 0.9
    ;(candidate.score_breakdown as unknown as Record<string, number>).role_match = 0.9
    ;(candidate.score_breakdown as unknown as Record<string, number>).skill_match = 0.9
    ;(candidate.score_breakdown as unknown as Record<string, number>).availability_score = 0.9
    ;(candidate.score_breakdown as unknown as Record<string, number>).workload_fit = 0.9
    ;(candidate.score_breakdown as unknown as Record<string, number>).authority_match = 0.9
    ;(candidate.score_breakdown as unknown as Record<string, number>).total_score = 0.9
    ;(candidate as unknown as { current_workload_percentage: number }).current_workload_percentage = 10
    ;(candidate as unknown as { projected_workload_percentage: number }).projected_workload_percentage = 20
    withNumbers.recommendation.confidence = 0.7 as unknown as string

    const parsed = parseProcessAgent3Allocation(withNumbers)
    expect(parsed).not.toBeNull()
    expect(parsed?.recommendation.confidence).toBe('0.7')
    expect(parsed?.recommendation.human_requirement_result?.eligible_candidates[0]?.allocation_score).toBe(
      '0.9',
    )
  })

  it('rejects unrelated workflow payloads', () => {
    expect(parseProcessAgent3Allocation({ overall_risk_level: 'HIGH' })).toBeNull()
  })
})
