import { useEffect, useId, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/cn';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  className?: string;
  /** Max width of dialog panel. Defaults to 'max-w-lg' */
  maxWidth?: string;
}

/**
 * Overlay rendered via portal. z-index is below CustomCursor (2147483646+) so the custom
 * cursor stays visible on top. Native `<dialog showModal()>` uses the top layer and was
 * painting above the cursor, so the pointer looked invisible over modals.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  className,
  maxWidth = 'max-w-lg',
}: ModalProps) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[2147483645]"
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? titleId : undefined}
    >
      <div
        role="presentation"
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative z-10 flex min-h-full items-start justify-center px-4 pb-4 pt-[8vh] pointer-events-none">
        <div
          className={cn(
            'pointer-events-auto w-full rounded-lg bg-white shadow-lg',
            'max-h-[calc(100vh-2rem)] overflow-y-auto',
            maxWidth,
            'animate-in fade-in',
            className,
          )}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="p-6">
            {title && (
              <div className="mb-4 flex items-center justify-between">
                <h2 id={titleId} className="text-lg font-semibold text-slate-900">
                  {title}
                </h2>
                <button
                  onClick={onClose}
                  className="-mr-1 p-1 text-slate-400 transition-colors hover:text-slate-600"
                  aria-label="Close"
                  type="button"
                >
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )}

            {children}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
