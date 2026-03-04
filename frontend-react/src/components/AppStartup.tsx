import { useAppConfig } from '@/api/endpoints/config';

/**
 * Warms the React Query cache for global config on app load.
 * Must be mounted inside QueryClientProvider and AuthProvider.
 */
export function AppStartup() {
  useAppConfig();
  return null;
}
