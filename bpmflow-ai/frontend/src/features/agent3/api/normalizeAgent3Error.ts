/**
 * Agent 3 Error Normalization
 *
 * This module normalizes backend errors into a safe frontend error contract.
 * It handles both Agent 3 route errors and FastAPI validation errors.
 *
 * Normalized error kind:
 * - authentication: 401
 * - authorization: 403
 * - not_found: 404
 * - conflict: 409
 * - validation: 422
 * - unavailable: 503
 * - unexpected: other errors
 */

import { AxiosError } from 'axios';
import type { FastAPIValidationErrorResponse } from '../types/agent3Api';

// ============================================================================
// Normalized Error Contract
// ============================================================================

export type ErrorKind =
  | 'authentication'
  | 'authorization'
  | 'not_found'
  | 'conflict'
  | 'validation'
  | 'unavailable'
  | 'unexpected';

export interface Agent3ClientError {
  kind: ErrorKind;
  status: number | null;
  errorCode: string;
  message: string;
  retryable: boolean;
  fieldErrors?: Record<string, string[]>;
}

// ============================================================================
// Error Kind Mapping
// ============================================================================

function mapStatusToKind(status: number): ErrorKind {
  switch (status) {
    case 401:
      return 'authentication';
    case 403:
      return 'authorization';
    case 404:
      return 'not_found';
    case 409:
      return 'conflict';
    case 422:
      return 'validation';
    case 503:
      return 'unavailable';
    default:
      return 'unexpected';
  }
}

// ============================================================================
// Normalize Agent 3 Route Error
// ============================================================================

const SAFE_MESSAGES: Record<ErrorKind, string> = {
  authentication: 'Authentication is required',
  authorization: 'You are not authorized to perform this action',
  not_found: 'The requested recommendation was not found',
  conflict: 'The request conflicts with an existing recommendation',
  validation: 'Request validation failed',
  unavailable: 'The service is temporarily unavailable',
  unexpected: 'An unexpected error occurred',
};

const SAFE_CODES = new Set([
  'UNAUTHORIZED', 'TENANT_MISMATCH', 'RECOMMENDATION_NOT_FOUND', 'PERSISTENCE_CONFLICT',
  'PERSISTENCE_VALIDATION_ERROR', 'PERSISTENCE_TRANSACTION_ERROR', 'PERSISTENCE_ERROR',
  'SERVICE_UNAVAILABLE', 'INTERNAL_ERROR',
]);

function normalizeRouteError(detail: Record<string, unknown>, status: number): Agent3ClientError {
  const kind = mapStatusToKind(status);
  return {
    kind,
    status,
    errorCode: typeof detail.error_code === 'string' && SAFE_CODES.has(detail.error_code) ? detail.error_code : 'UNKNOWN_ERROR',
    message: SAFE_MESSAGES[kind],
    retryable: typeof detail.retryable === 'boolean' ? detail.retryable : status >= 500,
  };
}

// ============================================================================
// Normalize FastAPI Validation Error
// ============================================================================

function normalizeValidationError(
  response: FastAPIValidationErrorResponse,
  status: number
): Agent3ClientError {
  const fieldErrors: Record<string, string[]> = {};

  for (const validationError of response.detail) {
    // Extract field name from location array
    // Format: ["body", "field_name"] or ["body", "metadata", "tenant_id"]
    const loc = validationError.loc;
    if (loc.length >= 2 && loc[0] === 'body') {
      // Use the last element as the field name for nested paths
      const fieldName = loc[loc.length - 1] as string;
      if (!fieldErrors[fieldName]) {
        fieldErrors[fieldName] = [];
      }
      fieldErrors[fieldName].push('Invalid value');
    }
  }

  return {
    kind: 'validation',
    status,
    errorCode: 'VALIDATION_ERROR',
    message: 'Request validation failed',
    retryable: false,
    fieldErrors,
  };
}

// ============================================================================
// Main Normalization Function
// ============================================================================

/**
 * Normalize an Axios error into a safe Agent3ClientError.
 *
 * This function:
 * - Handles Agent 3 route errors with detail.error_code
 * - Handles FastAPI 422 validation errors with detail array
 * - Maps HTTP status codes to error kinds
 * - Never exposes raw Axios errors, tokens, or sensitive data
 * - Returns a generic safe error for malformed responses
 *
 * @param error - The Axios error to normalize
 * @returns Normalized Agent3ClientError
 */
export function normalizeAgent3Error(error: unknown): Agent3ClientError {
  if (!(error instanceof AxiosError)) {
    // Non-Axios error
    return {
      kind: 'unexpected',
      status: null,
      errorCode: 'UNKNOWN_ERROR',
      message: 'An unexpected error occurred',
      retryable: false,
    };
  }

  const status = error.response?.status;

  if (!status || !error.response?.data) {
    // No response or no data
    return {
      kind: 'unexpected',
      status: status || null,
      errorCode: 'NO_RESPONSE',
      message: 'No response from server',
      retryable: true,
    };
  }

  const data: unknown = error.response.data;
  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    return { kind: mapStatusToKind(status), status, errorCode: 'UNKNOWN_ERROR', message: SAFE_MESSAGES[mapStatusToKind(status)], retryable: status >= 500 };
  }
  const body = data as Record<string, unknown>;
  const detail = typeof body.detail === 'object' && body.detail !== null && !Array.isArray(body.detail)
    ? body.detail as Record<string, unknown>
    : body;

  // Check if it's an Agent 3 route error (has error_code)
  if (typeof detail.error_code === 'string') {
    try {
      return normalizeRouteError(detail, status);
    } catch {
      // If normalization fails, return generic error
      return {
        kind: mapStatusToKind(status),
        status,
        errorCode: 'PARSE_ERROR',
        message: 'Failed to parse error response',
        retryable: false,
      };
    }
  }

  // Check if it's a FastAPI validation error (has detail array)
  if (Array.isArray(body.detail)) {
    try {
      return normalizeValidationError(body as unknown as FastAPIValidationErrorResponse, status);
    } catch {
      // If normalization fails, return generic error
      return {
        kind: 'validation',
        status,
        errorCode: 'PARSE_ERROR',
        message: 'Failed to parse validation error',
        retryable: false,
      };
    }
  }

  // Unknown error format
  return {
    kind: mapStatusToKind(status),
    status,
    errorCode: 'UNKNOWN_ERROR',
    message: 'An unexpected error occurred',
    retryable: status >= 500,
  };
}
