/**
 * Loading State Utilities
 *
 * These helpers provide loading state primitives for Agent 3 operations.
 */

export type LoadingState = 'idle' | 'loading' | 'success' | 'error';

export interface LoadingStateConfig {
  isLoading: boolean;
  isSuccess: boolean;
  isError: boolean;
  isIdle: boolean;
}

/**
 * Get loading state configuration from a loading state value.
 *
 * @param state - The loading state
 * @returns Loading state configuration
 */
export function getLoadingStateConfig(state: LoadingState): LoadingStateConfig {
  return {
    isLoading: state === 'loading',
    isSuccess: state === 'success',
    isError: state === 'error',
    isIdle: state === 'idle'
  };
}

/**
 * Get loading message for a loading state.
 *
 * @param state - The loading state
 * @returns Loading message
 */
export function getLoadingMessage(state: LoadingState): string {
  switch (state) {
    case 'loading':
      return 'Processing...';
    case 'success':
      return 'Completed successfully';
    case 'error':
      return 'An error occurred';
    case 'idle':
    default:
      return 'Ready';
  }
}
