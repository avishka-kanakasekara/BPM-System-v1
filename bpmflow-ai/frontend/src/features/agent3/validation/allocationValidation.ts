import type { BudgetResourceRequirement, HumanResourceRequirement } from '../types/agent3Api';
import { isValidDecimal, parseDecimal } from '../utils/decimalStrings';
import { localDateTimeToISO8601 } from '../utils/timestamps';

export type AllocationMode = 'HUMAN' | 'BUDGET' | 'MIXED';
export type FieldErrors = Record<string, string>;

export interface HumanDraft {
  requiredRoles: string; mandatorySkills: string; preferredSkills: string;
  requiredAuthority: string; taskDeadline: string; estimatedEffortHours: string; processStage: string;
}
export interface BudgetDraft {
  requiredAmount: string; currency: string; costCentre: string; taskDeadline: string; processStage: string;
}

export const emptyHumanDraft: HumanDraft = { requiredRoles: '', mandatorySkills: '', preferredSkills: '', requiredAuthority: '', taskDeadline: '', estimatedEffortHours: '', processStage: '' };
export const emptyBudgetDraft: BudgetDraft = { requiredAmount: '', currency: '', costCentre: '', taskDeadline: '', processStage: '' };

/** Trims, removes empty values, and removes later exact duplicates while preserving case and order. */
export function normalizeCommaSeparated(value: string): string[] {
  return [...new Set(value.split(',').map((item) => item.trim()).filter(Boolean))];
}

function deadline(value: string, key: string, errors: FieldErrors): string | null {
  if (!value.trim()) { errors[key] = 'Enter a task deadline.'; return null; }
  try { return localDateTimeToISO8601(value); } catch { errors[key] = 'Enter a valid local date and time.'; return null; }
}

export function validateHumanDraft(draft: HumanDraft, requesterId: string): { value: HumanResourceRequirement | null; errors: FieldErrors } {
  const errors: FieldErrors = {};
  const taskDeadline = deadline(draft.taskDeadline, 'humanTaskDeadline', errors);
  if (!isValidDecimal(draft.estimatedEffortHours)) errors.humanEstimatedEffortHours = 'Enter a non-negative decimal value.';
  if (!draft.processStage.trim()) errors.humanProcessStage = 'Enter a process stage.';
  if (Object.keys(errors).length || !taskDeadline) return { value: null, errors };
  return { value: {
    resource_type: 'HUMAN', required_roles: normalizeCommaSeparated(draft.requiredRoles),
    mandatory_skills: normalizeCommaSeparated(draft.mandatorySkills), preferred_skills: normalizeCommaSeparated(draft.preferredSkills),
    required_authority: draft.requiredAuthority.trim() || null, requester_id: requesterId, task_deadline: taskDeadline,
    estimated_effort_hours: parseDecimal(draft.estimatedEffortHours), process_stage: draft.processStage.trim(),
  }, errors };
}

export function validateBudgetDraft(draft: BudgetDraft, requesterId: string): { value: BudgetResourceRequirement | null; errors: FieldErrors } {
  const errors: FieldErrors = {};
  const taskDeadline = deadline(draft.taskDeadline, 'budgetTaskDeadline', errors);
  if (!isValidDecimal(draft.requiredAmount)) errors.budgetRequiredAmount = 'Enter a non-negative decimal value.';
  if (!draft.currency.trim()) errors.budgetCurrency = 'Enter a currency.';
  if (!draft.processStage.trim()) errors.budgetProcessStage = 'Enter a process stage.';
  if (Object.keys(errors).length || !taskDeadline) return { value: null, errors };
  return { value: {
    resource_type: 'BUDGET', required_amount: parseDecimal(draft.requiredAmount), currency: draft.currency.trim(),
    cost_centre: draft.costCentre.trim() || null, requester_id: requesterId, task_deadline: taskDeadline,
    process_stage: draft.processStage.trim(),
  }, errors };
}
