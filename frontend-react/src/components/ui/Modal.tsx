import { useEffect, useRef, type ReactNode } from 'react';
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

export function Modal({
  open,
  onClose,
  title,
  children,
  className,
  maxWidth = 'max-w-lg',
}: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const handler = () => onClose();
    dialog.addEventListener('close', handler);

    return () => dialog.removeEventListener('close', handler);
  }, [onClose]);

  return (
    <dialog
      ref={dialogRef}
      className={cn(
        'fixed inset-0 z-[100] m-0 h-screen w-screen overflow-hidden border-none bg-transparent p-0',
        'backdrop:bg-black/40 backdrop:backdrop-blur-sm'
      )}
      onClick={(e) => {
        if (e.target === dialogRef.current) onClose();
      }}
    >
      <div className="flex h-full items-start justify-center px-4 pt-[8vh] pb-4">
        <div
          className={cn(
            'w-full rounded-lg bg-white shadow-lg',
            'max-h-[calc(100vh-2rem)] overflow-y-auto',
            maxWidth,
            'animate-in fade-in',
            className
          )}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="p-6">
            {title && (
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
                <button
                  onClick={onClose}
                  className="p-1 -mr-1 text-slate-400 transition-colors hover:text-slate-600"
                  aria-label="Close"
                  type="button"
                >
                  <svg
                    className="h-5 w-5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>
            )}

            {children}
          </div>
        </div>
      </div>
    </dialog>
  );
}