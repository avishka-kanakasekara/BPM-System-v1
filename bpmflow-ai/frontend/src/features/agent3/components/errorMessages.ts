/**
 * Error Message Utilities
 *
 * These helpers provide safe error message mapping for Agent 3 errors.
 * They never expose raw Axios errors, tokens, or sensitive data.
 */

import type { Agent3ClientError } from '../api/normalizeAgent3Error';

// ============================================================================
// Error Message Configuration
// ============================================================================

export interface ErrorDisplay {
  title: string;
  message: string;
  actionText: string;
  showRetry: boolean;
}

/**
 * Get user-friendly error display information.
 *
 * @param error - The normalized Agent3ClientError
 * @returns Error display configuration
 */
export function getErrorDisplay(error: Agent3ClientError): ErrorDisplay {
  switch (error.kind) {
    case 'authentication':
      return {
        title: 'Authentication Required',
        message: 'Please sign in to access this feature.',
        actionText: 'Sign In',
        showRetry: false
      };
    case 'authorization':
      return {
        title: 'Access Denied',
        message: 'You do not have permission to perform this action.',
        actionText: 'Contact Support',
        showRetry: false
      };
    case 'not_found':
      return {
        title: 'Not Found',
        message: 'The requested resource was not found.',
        actionText: 'Go Back',
        showRetry: false
      };
    case 'conflict':
      return {
        title: 'Conflict',
        message: 'A recommendation for this request already exists.',
        actionText: 'View Existing',
        showRetry: false
      };
    case 'validation':
      return {
        title: 'Invalid Input',
        message: 'Please check your input and try again.',
        actionText: 'Fix Errors',
        showRetry: false
      };
    case 'unavailable':
      return {
        title: 'Service Unavailable',
        message: 'The service is temporarily unavailable. Please try again later.',
        actionText: 'Retry',
        showRetry: error.retryable
      };
    case 'unexpected':
    default:
      return {
        title: 'Unexpected Error',
        message: 'An unexpected error occurred. Please try again.',
        actionText: 'Retry',
        showRetry: error.retryable
      };
  }
}

/**
 * Get a safe error message for logging (never includes sensitive data).
 *
 * @param error - The normalized Agent3ClientError
 * @returns Safe error message for logging
 */
export function getSafeErrorMessage(error: Agent3ClientError): string {
  return `${error.kind}: ${error.errorCode} - ${error.message}`;
}
