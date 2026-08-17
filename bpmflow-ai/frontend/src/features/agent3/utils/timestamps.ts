/**
 * Timestamp Utilities
 *
 * These helpers handle ISO-8601 timestamp conversion and validation.
 * They ensure timezone-aware timestamps and reject invalid dates.
 */

// ============================================================================
// Timestamp Validation
// ============================================================================

/**
 * Validate an ISO-8601 timestamp string.
 *
 * @param value - The timestamp string to validate
 * @returns true if valid ISO-8601 with timezone, false otherwise
 */
export function isValidISO8601Timestamp(value: string): boolean {
  if (typeof value !== 'string') {
    return false;
  }

  try {
    const date = new Date(value);
    
    // Check if date is invalid
    if (isNaN(date.getTime())) {
      return false;
    }

    // Check if the string has timezone information (Z or offset)
    // ISO-8601 requires timezone for backend compatibility
    const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
    
    return hasTimezone;
  } catch {
    return false;
  }
}

/**
 * Convert a datetime-local input value to an ISO-8601 timestamp with timezone.
 *
 * @param localDateTime - The datetime-local input value (YYYY-MM-DDTHH:mm)
 * @param timezoneOffset - The timezone offset in minutes (e.g., -300 for UTC-5)
 * @returns ISO-8601 timestamp with timezone
 * @throws Error if invalid input
 */
export function localDateTimeToISO8601(
  localDateTime: string,
  timezoneOffset: number = new Date().getTimezoneOffset()
): string {
  if (!localDateTime) {
    throw new Error('datetime-local value is required');
  }

  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(localDateTime);
  if (!match) {
    throw new Error(`Invalid datetime-local value: ${localDateTime}`);
  }
  const [, year, month, day, hour, minute, second = '0'] = match;
  const utcDate = new Date(Date.UTC(+year, +month - 1, +day, +hour, +minute, +second) + timezoneOffset * 60000);
  if (utcDate.getUTCFullYear() !== +year && timezoneOffset === 0) throw new Error(`Invalid datetime-local value: ${localDateTime}`);
  return utcDate.toISOString();
}

/**
 * Display a timestamp in the user's local timezone.
 *
 * @param isoTimestamp - The ISO-8601 timestamp
 * @returns Formatted local date string
 */
export function formatTimestampToLocal(isoTimestamp: string): string {
  if (!isValidISO8601Timestamp(isoTimestamp)) {
    throw new Error(`Invalid ISO-8601 timestamp: ${isoTimestamp}`);
  }

  const date = new Date(isoTimestamp);
  
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short'
  });
}

/**
 * Get the current UTC timestamp as ISO-8601 string.
 *
 * @returns Current UTC timestamp
 */
export function getCurrentUTCTimestamp(): string {
  return new Date().toISOString();
}

/**
 * Parse an ISO-8601 timestamp to a Date object.
 *
 * @param isoTimestamp - The ISO-8601 timestamp
 * @returns Date object
 * @throws Error if invalid timestamp
 */
export function parseTimestamp(isoTimestamp: string): Date {
  if (!isValidISO8601Timestamp(isoTimestamp)) {
    throw new Error(`Invalid ISO-8601 timestamp: ${isoTimestamp}`);
  }

  return new Date(isoTimestamp);
}

/**
 * Check if a timestamp is in the past.
 *
 * @param isoTimestamp - The ISO-8601 timestamp
 * @returns true if timestamp is in the past, false otherwise
 */
export function isTimestampInPast(isoTimestamp: string): boolean {
  const date = parseTimestamp(isoTimestamp);
  const now = new Date();
  return date < now;
}

/**
 * Check if a timestamp is in the future.
 *
 * @param isoTimestamp - The ISO-8601 timestamp
 * @returns true if timestamp is in the future, false otherwise
 */
export function isTimestampInFuture(isoTimestamp: string): boolean {
  const date = parseTimestamp(isoTimestamp);
  const now = new Date();
  return date > now;
}
