import { cn } from '@/lib/cn';
import { ONBOARDING_DATA_USE } from './ethicsCopy';

type Props = {
  className?: string;
};

/**
 * Plain disclosure: only the title line is visible until opened — no card or button chrome.
 */
export function OnboardingDataUseCollapsible({ className }: Props) {
  const { title, sections } = ONBOARDING_DATA_USE;

  return (
    <details className={cn('group text-center', className)}>
      <summary
        className={cn(
          'cursor-pointer list-none inline-flex items-center justify-center gap-1.5 select-none',
          'text-sm text-[#5F7486] hover:text-[#16324A] transition-colors',
          '[&::-webkit-details-marker]:hidden',
        )}
      >
        <span className="border-b border-dotted border-[#5F7486]/50 group-hover:border-[#16324A]/40 pb-px">
          {title}
        </span>
        <svg
          className="h-3.5 w-3.5 shrink-0 text-[#78B3BA] transition-transform duration-200 group-open:rotate-180"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </summary>

      <div className="mt-3 text-left border-l-2 border-[#78B3BA]/25 pl-3 ml-0 sm:ml-1">
        <ul className="space-y-2.5">
          {sections.map((s) => (
            <li key={s.heading}>
              <h3 className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{s.heading}</h3>
              <p className="mt-0.5 text-[11px] leading-snug text-slate-600">{s.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}
