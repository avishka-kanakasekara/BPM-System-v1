/**
 * Decimal String Utilities
 *
 * These helpers provide string-safe decimal operations for monetary values.
 * They preserve exact decimal strings and avoid floating-point arithmetic.
 *
 * Rules:
 * - Never pass monetary values through Number, parseFloat, or floating-point arithmetic
 * - Preserve exact decimal strings
 * - Validate non-negative decimal input
 * - Allow formatting with explicitly supplied ISO currency code
 * - Avoid inventing currency symbols
 */

// ============================================================================
// Decimal Validation
// ============================================================================

/**
 * Validate a decimal string is non-negative and properly formatted.
 *
 * @param value - The decimal string to validate
 * @returns true if valid, false otherwise
 */
export function isValidDecimal(value: string): boolean {
  if (typeof value !== 'string') {
    return false;
  }

  // Remove leading/trailing whitespace
  const trimmed = value.trim();

  // Check if it's a valid decimal number (non-negative)
  const decimalRegex = /^\d+(\.\d+)?$/;
  return decimalRegex.test(trimmed);
}

/**
 * Validate and parse a decimal string.
 *
 * @param value - The decimal string to validate
 * @returns The trimmed decimal string if valid
 * @throws Error if invalid
 */
export function parseDecimal(value: string): string {
  if (!isValidDecimal(value)) {
    throw new Error(`Invalid decimal value: ${value}`);
  }
  return value.trim();
}

/**
 * Format a decimal string with a currency code.
 *
 * This does not add currency symbols - it only formats the decimal part.
 * Currency symbols should be added by the UI layer based on locale.
 *
 * @param value - The decimal string
 * @param currencyCode - ISO 4217 currency code (e.g., "USD", "EUR")
 * @returns Formatted string with currency code
 */
export function formatDecimalWithCurrency(
  value: string,
  currencyCode: string
): string {
  const parsed = parseDecimal(value);
  return `${parsed} ${currencyCode}`;
}

/**
 * Ensure a decimal string has exactly 2 decimal places.
 *
 * @param value - The decimal string
 * @returns Decimal string with 2 decimal places
 */
export function ensureTwoDecimalPlaces(value: string): string {
  const parsed = parseDecimal(value);
  
  if (parsed.includes('.')) {
    const parts = parsed.split('.');
    const integerPart = parts[0];
    const decimalPart = parts[1];
    
    if (decimalPart.length === 2) {
      return parsed;
    } else if (decimalPart.length === 1) {
      return `${integerPart}.${decimalPart}0`;
    } else if (decimalPart.length > 2) {
      // Truncate to 2 decimal places (no rounding for monetary precision)
      return `${integerPart}.${decimalPart.substring(0, 2)}`;
    }
  }
  
  // No decimal part, add ".00"
  return `${parsed}.00`;
}

/**
 * Add two decimal strings without floating-point arithmetic.
 *
 * @param a - First decimal string
 * @param b - Second decimal string
 * @returns Sum as decimal string
 */
export function addDecimals(a: string, b: string): string {
  const parsedA = parseDecimal(a);
  const parsedB = parseDecimal(b);
  
  // Convert to cents (multiply by 100)
  const toCents = (val: string): bigint => {
    const parts = val.split('.');
    const integer = BigInt(parts[0]);
    const decimal = parts.length > 1 ? parts[1].padEnd(2, '0').substring(0, 2) : '00';
    return integer * 100n + BigInt(decimal);
  };
  
  const centsA = toCents(parsedA);
  const centsB = toCents(parsedB);
  const sumCents = centsA + centsB;
  
  // Convert back to decimal string
  const integer = sumCents / 100n;
  const decimal = (sumCents % 100n).toString().padStart(2, '0');
  
  return `${integer}.${decimal}`;
}

/**
 * Compare two decimal strings.
 *
 * @param a - First decimal string
 * @param b - Second decimal string
 * @returns -1 if a < b, 0 if a === b, 1 if a > b
 */
export function compareDecimals(a: string, b: string): -1 | 0 | 1 {
  const parsedA = parseDecimal(a);
  const parsedB = parseDecimal(b);
  
  // Pad to same length for string comparison
  const maxLength = Math.max(parsedA.length, parsedB.length);
  const paddedA = parsedA.padStart(maxLength, '0');
  const paddedB = parsedB.padStart(maxLength, '0');
  
  if (paddedA < paddedB) return -1;
  if (paddedA > paddedB) return 1;
  return 0;
}
