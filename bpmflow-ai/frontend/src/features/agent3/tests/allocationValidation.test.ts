import { describe, expect, it } from 'vitest';
import { emptyBudgetDraft, emptyHumanDraft, normalizeCommaSeparated, validateBudgetDraft, validateHumanDraft } from '../validation/allocationValidation';

const requester = '00000000-0000-0000-0000-000000000002';
const human = { ...emptyHumanDraft, taskDeadline: '2020-01-01T12:00', estimatedEffortHours: '0.8750', processStage: ' Review ' };
const budget = { ...emptyBudgetDraft, requiredAmount: '9999999999999999.99', currency: ' credits ', taskDeadline: '2020-01-01T12:00', processStage: ' Review ' };

describe('allocation validation', () => {
  it('normalizes comma-separated values deterministically', () => expect(normalizeCommaSeparated(' Lead, ,QA,Lead, lead ')).toEqual(['Lead', 'QA', 'lead']));
  it('allows empty human arrays', () => expect(validateHumanDraft(human, requester).value?.required_roles).toEqual([]));
  it('preserves human effort exactly', () => expect(validateHumanDraft(human, requester).value?.estimated_effort_hours).toBe('0.8750'));
  it('allows zero human effort', () => expect(validateHumanDraft({ ...human, estimatedEffortHours: '0' }, requester).value).not.toBeNull());
  it('rejects invalid human effort', () => expect(validateHumanDraft({ ...human, estimatedEffortHours: '-1' }, requester).errors.humanEstimatedEffortHours).toBeDefined());
  it('rejects missing human deadline', () => expect(validateHumanDraft({ ...human, taskDeadline: '' }, requester).errors.humanTaskDeadline).toBeDefined());
  it('rejects invalid human deadline', () => expect(validateHumanDraft({ ...human, taskDeadline: 'bad' }, requester).errors.humanTaskDeadline).toBeDefined());
  it('accepts a past human deadline', () => expect(validateHumanDraft(human, requester).value).not.toBeNull());
  it('trims authority and stage', () => expect(validateHumanDraft({ ...human, requiredAuthority: ' Lead ' }, requester).value).toMatchObject({ required_authority: 'Lead', process_stage: 'Review' }));
  it('serializes empty authority as null', () => expect(validateHumanDraft(human, requester).value?.required_authority).toBeNull());
  it('preserves a large budget Decimal', () => expect(validateBudgetDraft(budget, requester).value?.required_amount).toBe('9999999999999999.99'));
  it('allows zero budget amount', () => expect(validateBudgetDraft({ ...budget, requiredAmount: '0' }, requester).value).not.toBeNull());
  it('rejects invalid budget amount', () => expect(validateBudgetDraft({ ...budget, requiredAmount: '$20' }, requester).errors.budgetRequiredAmount).toBeDefined());
  it('requires non-empty currency only', () => expect(validateBudgetDraft({ ...budget, currency: 'X' }, requester).value?.currency).toBe('X'));
  it('rejects empty currency', () => expect(validateBudgetDraft({ ...budget, currency: ' ' }, requester).errors.budgetCurrency).toBeDefined());
  it('serializes empty cost centre as null', () => expect(validateBudgetDraft(budget, requester).value?.cost_centre).toBeNull());
  it('preserves supplied cost centre', () => expect(validateBudgetDraft({ ...budget, costCentre: ' CC-1 ' }, requester).value?.cost_centre).toBe('CC-1'));
  it('uses the authenticated requester in both contracts', () => {
    expect(validateHumanDraft(human, requester).value?.requester_id).toBe(requester);
    expect(validateBudgetDraft(budget, requester).value?.requester_id).toBe(requester);
  });
});
