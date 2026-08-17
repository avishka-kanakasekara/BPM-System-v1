/**
 * Agent 3 Utilities Tests
 *
 * Tests for decimal strings, timestamps, and metadata utilities.
 */

import { describe, it, expect } from 'vitest';
import {
  isValidDecimal,
  parseDecimal,
  ensureTwoDecimalPlaces,
  addDecimals,
  compareDecimals
} from '../utils/decimalStrings';
import {
  isValidISO8601Timestamp,
  localDateTimeToISO8601,
  formatTimestampToLocal,
  getCurrentUTCTimestamp,
  isTimestampInPast,
  isTimestampInFuture
} from '../utils/timestamps';
import {
  generateUUID,
  isValidUUID,
  generateCorrelationId,
  preserveCorrelationId,
  generateWorkflowId,
  useWorkflowId,
  createMessageMetadata
} from '../utils/metadata';

describe('Decimal String Utilities', () => {
  describe('isValidDecimal', () => {
    it('should validate valid decimal strings', () => {
      expect(isValidDecimal('100')).toBe(true);
      expect(isValidDecimal('100.50')).toBe(true);
      expect(isValidDecimal('0.01')).toBe(true);
      expect(isValidDecimal('0')).toBe(true);
    });

    it('should reject invalid decimal strings', () => {
      expect(isValidDecimal('')).toBe(false);
      expect(isValidDecimal('-100')).toBe(false);
      expect(isValidDecimal('abc')).toBe(false);
      expect(isValidDecimal('100.50.50')).toBe(false);
      expect(isValidDecimal('100.')).toBe(false);
    });
  });

  describe('parseDecimal', () => {
    it('should parse valid decimal strings', () => {
      expect(parseDecimal('100')).toBe('100');
      expect(parseDecimal('100.50')).toBe('100.50');
    });

    it('should throw on invalid decimal strings', () => {
      expect(() => parseDecimal('abc')).toThrow('Invalid decimal value');
    });
  });

  describe('ensureTwoDecimalPlaces', () => {
    it('should add decimal places if missing', () => {
      expect(ensureTwoDecimalPlaces('100')).toBe('100.00');
    });

    it('should pad single decimal place', () => {
      expect(ensureTwoDecimalPlaces('100.5')).toBe('100.50');
    });

    it('should truncate to two decimal places', () => {
      expect(ensureTwoDecimalPlaces('100.555')).toBe('100.55');
    });

    it('should leave two decimal places unchanged', () => {
      expect(ensureTwoDecimalPlaces('100.50')).toBe('100.50');
    });
  });

  describe('addDecimals', () => {
    it('should add two decimal strings correctly', () => {
      expect(addDecimals('100.50', '50.25')).toBe('150.75');
      expect(addDecimals('0.01', '0.99')).toBe('1.00');
    });

    it('should handle whole numbers', () => {
      expect(addDecimals('100', '50')).toBe('150.00');
    });

    it('preserves values beyond JavaScript safe integer precision', () => {
      expect(addDecimals('9999999999999999.99', '0.01')).toBe('10000000000000000.00');
    });
  });

  describe('compareDecimals', () => {
    it('should return -1 when a < b', () => {
      expect(compareDecimals('50', '100')).toBe(-1);
    });

    it('should return 0 when a === b', () => {
      expect(compareDecimals('100', '100')).toBe(0);
    });

    it('should return 1 when a > b', () => {
      expect(compareDecimals('100', '50')).toBe(1);
    });
  });
});

describe('Timestamp Utilities', () => {
  describe('isValidISO8601Timestamp', () => {
    it('should validate ISO-8601 timestamps with timezone', () => {
      expect(isValidISO8601Timestamp('2026-01-01T12:00:00Z')).toBe(true);
      expect(isValidISO8601Timestamp('2026-01-01T12:00:00+05:30')).toBe(true);
    });

    it('should reject timestamps without timezone', () => {
      expect(isValidISO8601Timestamp('2026-01-01T12:00:00')).toBe(false);
    });

    it('should reject invalid timestamps', () => {
      expect(isValidISO8601Timestamp('invalid')).toBe(false);
    });
  });

  describe('localDateTimeToISO8601', () => {
    it('should convert datetime-local to ISO-8601', () => {
      const result = localDateTimeToISO8601('2026-01-01T12:00', 0);
      expect(result).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
    });

    it('should throw on invalid input', () => {
      expect(() => localDateTimeToISO8601('invalid')).toThrow('Invalid datetime-local value');
    });
  });

  describe('formatTimestampToLocal', () => {
    it('should format ISO timestamp to local string', () => {
      const result = formatTimestampToLocal('2026-01-01T12:00:00Z');
      expect(typeof result).toBe('string');
    });

    it('should throw on invalid timestamp', () => {
      expect(() => formatTimestampToLocal('invalid')).toThrow('Invalid ISO-8601 timestamp');
    });
  });

  describe('getCurrentUTCTimestamp', () => {
    it('should return current UTC timestamp', () => {
      const result = getCurrentUTCTimestamp();
      expect(isValidISO8601Timestamp(result)).toBe(true);
    });
  });

  describe('isTimestampInPast', () => {
    it('should detect past timestamps', () => {
      expect(isTimestampInPast('2020-01-01T12:00:00Z')).toBe(true);
    });

    it('should detect future timestamps', () => {
      expect(isTimestampInPast('2030-01-01T12:00:00Z')).toBe(false);
    });
  });

  describe('isTimestampInFuture', () => {
    it('should detect future timestamps', () => {
      expect(isTimestampInFuture('2030-01-01T12:00:00Z')).toBe(true);
    });

    it('should detect past timestamps', () => {
      expect(isTimestampInFuture('2020-01-01T12:00:00Z')).toBe(false);
    });
  });
});

describe('Metadata Utilities', () => {
  describe('UUID generation and validation', () => {
    it('should generate valid UUIDs', () => {
      const uuid = generateUUID();
      expect(isValidUUID(uuid)).toBe(true);
    });

    it('should validate valid UUIDs', () => {
      expect(isValidUUID('00000000-0000-0000-0000-000000000001')).toBe(true);
    });

    it('should reject invalid UUIDs', () => {
      expect(isValidUUID('invalid')).toBe(false);
      expect(isValidUUID('00000000-0000-0000-0000-00000000000')).toBe(false);
    });
  });

  describe('Correlation ID management', () => {
    it('should generate correlation IDs', () => {
      const correlationId = generateCorrelationId();
      expect(isValidUUID(correlationId)).toBe(true);
    });

    it('should preserve valid correlation IDs', () => {
      const correlationId = preserveCorrelationId('00000000-0000-0000-0000-000000000001');
      expect(correlationId).toBe('00000000-0000-0000-0000-000000000001');
    });

    it('should throw on invalid correlation IDs', () => {
      expect(() => preserveCorrelationId('invalid')).toThrow('Invalid correlation ID');
    });
  });

  describe('Workflow ID management', () => {
    it('should generate workflow IDs', () => {
      const workflowId = generateWorkflowId();
      expect(isValidUUID(workflowId)).toBe(true);
    });

    it('should use trusted workflow IDs when provided', () => {
      const workflowId = useWorkflowId('00000000-0000-0000-0000-000000000001');
      expect(workflowId).toBe('00000000-0000-0000-0000-000000000001');
    });

    it('should generate demo fallback when no trusted ID provided', () => {
      const workflowId = useWorkflowId(null);
      expect(isValidUUID(workflowId)).toBe(true);
    });

    it('should throw on invalid workflow IDs', () => {
      expect(() => useWorkflowId('invalid')).toThrow('Invalid workflow ID');
    });
  });

  describe('Message metadata creation', () => {
    it('should create message metadata with valid parameters', () => {
      const metadata = createMessageMetadata({
        tenantId: '00000000-0000-0000-0000-000000000001',
        correlationId: '00000000-0000-0000-0000-000000000002',
        processInstanceId: '00000000-0000-0000-0000-000000000003',
        taskId: '00000000-0000-0000-0000-000000000004'
      });

      expect(metadata.tenant_id).toBe('00000000-0000-0000-0000-000000000001');
      expect(metadata.correlation_id).toBe('00000000-0000-0000-0000-000000000002');
      expect(metadata.schema_version).toBe('1.0.0');
      expect(metadata.sender).toBe('agent3');
      expect(metadata.receiver).toBe('agent4');
      expect(isValidUUID(metadata.message_id)).toBe(true);
    });

    it('should throw on invalid tenant ID', () => {
      expect(() => createMessageMetadata({
        tenantId: 'invalid',
        correlationId: '00000000-0000-0000-0000-000000000002',
        processInstanceId: null,
        taskId: null
      })).toThrow('Invalid tenant ID');
    });

    it('should throw on invalid correlation ID', () => {
      expect(() => createMessageMetadata({
        tenantId: '00000000-0000-0000-0000-000000000001',
        correlationId: 'invalid',
        processInstanceId: null,
        taskId: null
      })).toThrow('Invalid correlation ID');
    });

    it('should use demo fallback for workflow IDs when null', () => {
      const metadata = createMessageMetadata({
        tenantId: '00000000-0000-0000-0000-000000000001',
        correlationId: '00000000-0000-0000-0000-000000000002',
        processInstanceId: null,
        taskId: null
      });

      expect(isValidUUID(metadata.process_instance_id)).toBe(true);
      expect(isValidUUID(metadata.task_id)).toBe(true);
    });
  });
});
