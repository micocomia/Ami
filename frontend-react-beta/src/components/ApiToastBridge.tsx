import { useEffect } from 'react';
import { useToast } from '@/components/ui/Toast';
import { setToastHandler } from '@/api/toast';

/**
 * Render this once inside ToastProvider to wire API-layer
 * toast calls (showError/showSuccess) to the real UI toasts.
 */
export function ApiToastBridge() {
  const { toast } = useToast();
  useEffect(() => {
    setToastHandler(toast);
    return () => setToastHandler(() => {});
  }, [toast]);
  return null;
}
