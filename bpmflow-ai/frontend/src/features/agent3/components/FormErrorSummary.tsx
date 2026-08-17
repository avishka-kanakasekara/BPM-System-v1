import { forwardRef } from 'react';
import type { FieldErrors } from '../validation/allocationValidation';

export const FormErrorSummary = forwardRef<HTMLDivElement, { errors: FieldErrors }>(({ errors }, ref) => {
  if (!Object.keys(errors).length) return null;
  return <div ref={ref} tabIndex={-1} role="alert" aria-labelledby="form-errors-title" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
    <h2 id="form-errors-title" className="font-semibold">Please correct the following fields</h2>
    <ul className="mt-2 list-disc pl-5">{Object.entries(errors).map(([key, message]) => <li key={key}><a className="underline" href={`#${key}`}>{message}</a></li>)}</ul>
  </div>;
});
FormErrorSummary.displayName = 'FormErrorSummary';
