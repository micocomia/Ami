import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { cn } from '@/lib/cn';

export type ToastVariant = 'success' | 'error' | 'info' | 'loading';

interface ToastItem {
  id: number;
  variant: ToastVariant;
  message: string;
}

interface ToastContextValue {
  toast: (variant: ToastVariant, message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within <ToastProvider>');
  return ctx;
}

const AUTO_DISMISS_MS = 4000;

const variantIcon: Record<ToastVariant, string> = {
  success: '✓',
  error: '✕',
  info: 'ℹ',
  loading: '⟳',
};

const variantClasses: Record<ToastVariant, string> = {
  success: 'border-l-success-500 bg-success-50 text-success-700',
  error: 'border-l-danger-500 bg-danger-50 text-danger-700',
  info: 'border-l-primary-500 bg-primary-50 text-primary-700',
  loading: 'border-l-warning-500 bg-warning-50 text-slate-700',
};

let nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const toast = useCallback(
    (variant: ToastVariant, message: string) => {
      const id = ++nextId;
      setItems((prev) => [...prev, { id, variant, message }]);
      if (variant !== 'loading') {
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), AUTO_DISMISS_MS),
        );
      }
    },
    [dismiss],
  );

  useEffect(() => {
    return () => {
      timers.current.forEach(clearTimeout);
    };
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        aria-live="polite"
        className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-80 pointer-events-none"
      >
        {items.map((t) => (
          <div
            key={t.id}
            className={cn(
              'pointer-events-auto border-l-4 rounded-md shadow-md px-4 py-3 flex items-start gap-2 text-sm',
              variantClasses[t.variant],
            )}
          >
            <span className="font-bold text-base leading-5 shrink-0">
              {variantIcon[t.variant]}
            </span>
            <span className="flex-1 break-words">{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              className="shrink-0 text-current opacity-50 hover:opacity-100"
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
