/**
 * Metadata Utilities
 *
 * These helpers provide UUID generation, correlation ID management,
 * and message metadata creation for Agent 3 requests.
 */

// ============================================================================
// UUID Generation and Validation
// ============================================================================

/**
 * Generate a random UUID v4.
 *
 * Uses the browser's crypto.randomUUID() API.
 *
 * @returns A random UUID string
 */
export function generateUUID(): string {
  return crypto.randomUUID();
}

/**
 * Validate a UUID string.
 *
 * @param uuid - The UUID string to validate
 * @returns true if valid, false otherwise
 */
export function isValidUUID(uuid: string): boolean {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(uuid);
}

// ============================================================================
// Correlation ID Management
// ============================================================================

/**
 * Generate a new correlation ID.
 *
 * @returns A new correlation ID UUID
 */
export function generateCorrelationId(): string {
  return generateUUID();
}

/**
 * Preserve an existing correlation ID.
 *
 * @param correlationId - The existing correlation ID
 * @returns The same correlation ID if valid
 * @throws Error if invalid
 */
export function preserveCorrelationId(correlationId: string): string {
  if (!isValidUUID(correlationId)) {
    throw new Error(`Invalid correlation ID: ${correlationId}`);
  }
  return correlationId;
}

// ============================================================================
// Workflow ID Management
// ============================================================================

/**
 * Generate a workflow ID (process_instance_id or task_id).
 *
 * IMPORTANT: In production, these should come from trusted workflow context.
 * Random generation is only for standalone/demo scenarios.
 *
 * @returns A workflow ID UUID
 */
export function generateWorkflowId(): string {
  return generateUUID();
}

/**
 * Use a trusted workflow ID if provided, otherwise generate a demo fallback.
 *
 * @param trustedId - The trusted workflow ID from context (optional)
 * @returns The trusted ID if provided, otherwise a generated demo ID
 */
export function useWorkflowId(trustedId: string | null): string {
  if (trustedId) {
    if (!isValidUUID(trustedId)) {
      throw new Error(`Invalid workflow ID: ${trustedId}`);
    }
    return trustedId;
  }
  
  // Demo fallback - explicitly marked
  console.warn('Using randomly generated workflow ID (demo fallback only)');
  return generateWorkflowId();
}

// ============================================================================
// Message Metadata Creation
// ============================================================================

// Fixed schema and message values from backend constants
const SCHEMA_VERSION = '1.0.0';
const AGENT_3_SENDER = 'agent3';
const AGENT_4_RECEIVER = 'agent4';
const MESSAGE_TYPE = 'RESOURCE_ALLOCATION_REQUEST';

/**
 * Create Agent 3 message metadata.
 *
 * @param tenantId - The tenant ID from session
 * @param correlationId - The correlation ID (generated or preserved)
 * @param processInstanceId - The process instance ID from workflow context
 * @param taskId - The task ID from workflow context
 * @returns Agent message metadata object
 */
export interface MessageMetadataParams {
  tenantId: string;
  correlationId: string;
  processInstanceId: string | null;
  taskId: string | null;
}

export function createMessageMetadata(params: MessageMetadataParams) {
  const { tenantId, correlationId, processInstanceId, taskId } = params;

  // Validate required fields
  if (!isValidUUID(tenantId)) {
    throw new Error(`Invalid tenant ID: ${tenantId}`);
  }

  if (!isValidUUID(correlationId)) {
    throw new Error(`Invalid correlation ID: ${correlationId}`);
  }

  // Use workflow IDs with demo fallback
  const finalProcessInstanceId = useWorkflowId(processInstanceId);
  const finalTaskId = useWorkflowId(taskId);

  return {
    message_id: generateUUID(),
    schema_version: SCHEMA_VERSION,
    correlation_id: correlationId,
    process_instance_id: finalProcessInstanceId,
    task_id: finalTaskId,
    tenant_id: tenantId,
    sender: AGENT_3_SENDER,
    receiver: AGENT_4_RECEIVER,
    message_type: MESSAGE_TYPE,
    timestamp: getCurrentUTCTimestamp()
  };
}

/**
 * Get the current UTC timestamp as ISO-8601 string.
 *
 * @returns Current UTC timestamp
 */
function getCurrentUTCTimestamp(): string {
  return new Date().toISOString();
}
