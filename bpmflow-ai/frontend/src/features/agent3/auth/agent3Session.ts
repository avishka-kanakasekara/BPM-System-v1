/**
 * Secure Session Adapter for Agent 3
 *
 * This module provides secure access to Supabase session data for Agent 3 operations.
 * It enforces strict security boundaries:
 * - Never stores access tokens in localStorage, React state, or logs
 * - Never manually decodes JWTs
 * - Never uses user_metadata for tenant authorization
 * - Fails closed when session is invalid or missing required data
 * - Only reads from app_metadata.tenant_id for tenant authorization
 */

import { supabase } from '../../../services/supabaseClient';

// ============================================================================
// Session Error Types
// ============================================================================

export class SessionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SessionError';
  }
}

// ============================================================================
// Session Data Interface
// ============================================================================

export interface Agent3SessionData {
  requesterId: string;
  tenantId: string;
  accessToken: string;
}

// ============================================================================
// UUID Validation
// ============================================================================

function isValidUUID(uuid: string): boolean {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(uuid);
}

// ============================================================================
// Session Adapter
// ============================================================================

/**
 * Get the current Agent 3 session data securely.
 *
 * This function:
 * - Obtains the current managed session from Supabase
 * - Validates that the session is authenticated
 * - Extracts requester ID from session.user.id
 * - Extracts tenant ID from session.user.app_metadata.tenant_id (NOT user_metadata)
 * - Validates both IDs as UUID strings
 * - Returns one request-scoped snapshot of identity, tenant, and access token
 *
 * @throws SessionError if session is invalid or missing required data
 * @returns Agent3SessionData with requester ID, tenant ID, and token getter
 */
export async function getAgent3Session(): Promise<Agent3SessionData> {
  // Get current session from Supabase
  const { data: { session }, error: sessionError } = await supabase.auth.getSession();

  if (sessionError) {
    throw new SessionError('Failed to retrieve session');
  }

  if (!session) {
    throw new SessionError('No authenticated session exists');
  }

  // Validate access token exists
  if (!session.access_token) {
    throw new SessionError('Access token is missing from session');
  }

  // Validate user exists
  if (!session.user) {
    throw new SessionError('User data is missing from session');
  }

  // Validate requester ID (user.id) as UUID
  const requesterId = session.user.id;
  if (!requesterId || !isValidUUID(requesterId)) {
    throw new SessionError('Invalid requester ID in session');
  }

  // Validate tenant ID from app_metadata (NOT user_metadata)
  const tenantId = session.user.app_metadata?.tenant_id;
  if (!tenantId || typeof tenantId !== 'string' || !isValidUUID(tenantId)) {
    throw new SessionError('Invalid or missing tenant ID in session app_metadata');
  }

  return {
    requesterId,
    tenantId,
    accessToken: session.access_token,
  };
}

/**
 * Check if a valid Agent 3 session exists without throwing.
 *
 * This is useful for conditional UI rendering without error handling.
 *
 * @returns true if a valid session exists, false otherwise
 */
export async function hasValidAgent3Session(): Promise<boolean> {
  try {
    await getAgent3Session();
    return true;
  } catch {
    return false;
  }
}
