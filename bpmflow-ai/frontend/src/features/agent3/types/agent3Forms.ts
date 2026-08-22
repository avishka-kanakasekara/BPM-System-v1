/**
 * Form-specific types for Agent 3 UI
 *
 * These types are used for form inputs and validation in the UI layer.
 * They map to the API types but may have additional UI-specific fields.
 */

// ============================================================================
// Human Requirement Form
// ============================================================================

export interface HumanRequirementForm {
  resource_type: 'HUMAN';
  required_roles: string[];
  mandatory_skills: string[];
  preferred_skills: string[];
  required_authority: string;
  requester_id: string; // Read-only from session
  task_deadline: string; // datetime-local input format
  estimated_effort_hours: string; // Decimal as string
  process_stage: string;
}

// ============================================================================
// Budget Requirement Form
// ============================================================================

export interface BudgetRequirementForm {
  resource_type: 'BUDGET';
  required_amount: string; // Decimal as string
  currency: string;
  cost_centre: string;
  requester_id: string; // Read-only from session
  task_deadline: string; // datetime-local input format
  process_stage: string;
}

// ============================================================================
// Allocation Request Form
// ============================================================================

export interface AllocationRequestForm {
  correlation_id: string; // Generated or from workflow context
  process_instance_id: string; // From workflow context
  task_id: string; // From workflow context
  tenant_id: string; // Read-only from session
  human_requirements: HumanRequirementForm | null;
  budget_requirements: BudgetRequirementForm | null;
}

// ============================================================================
// Form Validation Errors
// ============================================================================

export interface FormFieldError {
  message: string;
}

export interface FormErrors {
  [fieldName: string]: FormFieldError | undefined;
}

// ============================================================================
// Form State
// ============================================================================

export type FormStatus = 'idle' | 'validating' | 'submitting' | 'success' | 'error';

export interface AllocationFormState {
  status: FormStatus;
  values: AllocationRequestForm;
  errors: FormErrors;
  touched: Record<string, boolean>;
}
