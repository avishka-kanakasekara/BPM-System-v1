/**
 * Status Label Utilities
 *
 * These helpers provide status-to-label mappings for Agent 3 recommendations.
 * They combine color with text for accessibility.
 */

// ============================================================================
// Status Label Configuration
// ============================================================================

export interface StatusLabel {
  text: string;
  colorClass: string;
  bgColorClass: string;
  icon: string;
}

/**
 * Get status label configuration for a recommendation status.
 *
 * @param status - The recommendation status
 * @returns Status label with text, color, and icon
 */
export function getStatusLabel(status: string): StatusLabel {
  switch (status) {
    case 'GENERATED':
      return {
        text: 'Generated',
        colorClass: 'text-emerald-600',
        bgColorClass: 'bg-emerald-50',
        icon: '✓'
      };
    case 'PENDING_HUMAN_APPROVAL':
      return {
        text: 'Pending Approval',
        colorClass: 'text-amber-600',
        bgColorClass: 'bg-amber-50',
        icon: '⏱'
      };
    case 'SUPERSEDED':
      return {
        text: 'Superseded',
        colorClass: 'text-slate-600',
        bgColorClass: 'bg-slate-50',
        icon: '↻'
      };
    case 'FAILED':
      return {
        text: 'Failed',
        colorClass: 'text-red-600',
        bgColorClass: 'bg-red-50',
        icon: '✕'
      };
    default:
      return {
        text: 'Unknown',
        colorClass: 'text-slate-600',
        bgColorClass: 'bg-slate-50',
        icon: '?'
      };
  }
}

/**
 * Get human-readable status text.
 *
 * @param status - The recommendation status
 * @returns Human-readable status text
 */
export function getStatusText(status: string): string {
  return getStatusLabel(status).text;
}

/**
 * Check if a status is a success status.
 *
 * @param status - The recommendation status
 * @returns true if status is GENERATED or PENDING_HUMAN_APPROVAL
 */
export function isSuccessStatus(status: string): boolean {
  return status === 'GENERATED' || status === 'PENDING_HUMAN_APPROVAL';
}

/**
 * Check if a status is a failure status.
 *
 * @param status - The recommendation status
 * @returns true if status is FAILED
 */
export function isFailureStatus(status: string): boolean {
  return status === 'FAILED';
}

/**
 * Check if a status requires human approval.
 *
 * @param status - The recommendation status
 * @returns true if status is PENDING_HUMAN_APPROVAL
 */
export function requiresApproval(status: string): boolean {
  return status === 'PENDING_HUMAN_APPROVAL';
}
