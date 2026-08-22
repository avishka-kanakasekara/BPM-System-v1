import { isValidUUID } from '../utils/metadata';
export function validateLookupId(value: string): string | null { return isValidUUID(value.trim()) ? null : 'Enter a valid UUID.'; }
