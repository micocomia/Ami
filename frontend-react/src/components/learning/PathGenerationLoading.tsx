import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/cn';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const STEP_INTERVAL_MS = 4_000;
const TIP_INTERVAL_MS = 6_000;
const TIP_SHOW_DELAY_MS = 4_000;

/* ------------------------------------------------------------------ */
/*  Center loading glyph (subtle, cool-toned)                         */
/* ------------------------------------------------------------------ */

function CenterSpinner() {
  return (
    <div className="relative w-16 h-16 flex items-center justify-center">
      {/* Outer static ring */}
      <div className="absolute inset-0 rounded-full border border-[#DCE6F2] bg-[#F3F7FB]" />

      {/* Rotating arc */}
      <svg
        className="absolute w-full h-full animate-spin-slow text-[#5B8DEF]"
        viewBox="0 0 24 24"
      >
        <circle
          cx="12"
          cy="12"
          r="9"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeDasharray="40 40"
          strokeDashoffset="20"
          strokeLinecap="round"
        />
      </svg>

      {/* Inner core */}
      <div className="relative w-8 h-8 rounded-full bg-white border border-[#DCE6F2] flex items-center justify-center shadow-sm">
        {/* Simple brain/spark icon, cool-toned */}
        <svg className="w-5 h-5 text-[#5B8DEF]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z"
          />
        </svg>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step progress list                                                 */
/* ------------------------------------------------------------------ */

function StepProgress({ steps, activeIndex }: { steps: readonly string[]; activeIndex: number }) {
  if (!steps.length) return null;
  return (
    <ul className="space-y-2.5">
      {steps.map((msg, i) => {
        const done = i < activeIndex;
        const active = i === activeIndex;
        return (
          <li key={`${i}-${msg.slice(0, 20)}`} className="flex items-start gap-2.5 text-sm">
            {done ? (
              <svg
                className="w-4 h-4 mt-0.5 text-teal-500 shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            ) : active ? (
              <div className="w-4 h-4 mt-0.5 shrink-0 flex items-center justify-center">
                <div className="w-3 h-3 rounded-full border-2 border-[#5B8DEF] border-t-transparent animate-spin" />
              </div>
            ) : (
              <div className="w-4 h-4 mt-0.5 shrink-0 flex items-center justify-center">
                <div className="w-2 h-2 rounded-full bg-[#D0DEEF]" />
              </div>
            )}
            <span className={cn(
              done && 'text-teal-700',
              active && 'text-[#1F2A44] font-medium',
              !done && !active && 'text-[#A2B3CC]',
            )}>
              {msg}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/* ------------------------------------------------------------------ */
/*  Tip carousel                                                       */
/* ------------------------------------------------------------------ */

function TipCarousel({ tips }: { tips: readonly string[] }) {
  const [idx, setIdx] = useState(0);
  const [fadeIn, setFadeIn] = useState(true);

  useEffect(() => {
    if (tips.length <= 1) return;
    const id = setInterval(() => {
      setFadeIn(false);
      setTimeout(() => {
        setIdx((prev) => (prev + 1) % tips.length);
        setFadeIn(true);
      }, 250);
    }, TIP_INTERVAL_MS);
    return () => clearInterval(id);
  }, [tips.length]);

  if (!tips.length) return null;
  return (
    <div className="rounded-xl border border-[#DCE6F2] bg-[#F3F7FB] px-5 py-4 text-center">
      <p className="text-xs font-medium uppercase tracking-wider text-[#6B7A90] mb-2">
        Tip
      </p>
      <p
        className={cn(
          'text-sm text-[#4A5975] leading-relaxed transition-opacity duration-250',
          fadeIn ? 'opacity-100' : 'opacity-0',
        )}
      >
        {tips[idx]}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export interface PathGenerationLoadingProps {
  /** Main heading, e.g. "Building your learning path" or "Building your skill gap profile" */
  title: string;
  /** Optional short description under the title */
  subtitle?: string;
  /** Step messages shown in the checklist (e.g. "Analyzing your skill gaps…") */
  steps: readonly string[] | string[];
  /** Rotating tips shown below (e.g. "Tip: Clear goals lead to...") */
  tips: readonly string[] | string[];
  /** Optional goal/skill title shown under the main title (e.g. the user's goal text) */
  goalTitle?: string;
}

export function PathGenerationLoading({
  title,
  subtitle,
  steps,
  tips,
  goalTitle,
}: PathGenerationLoadingProps) {
  const [stepIndex, setStepIndex] = useState(0);
  const [showTips, setShowTips] = useState(false);
  const stepTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const tipTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stepCount = steps.length;

  // Advance steps (loop back to last step instead of overflowing)
  useEffect(() => {
    if (stepCount === 0) return;
    stepTimerRef.current = setInterval(() => {
      setStepIndex((prev) => Math.min(prev + 1, stepCount - 1));
    }, STEP_INTERVAL_MS);
    return () => {
      if (stepTimerRef.current) clearInterval(stepTimerRef.current);
    };
  }, [stepCount]);

  // Delayed tips
  useEffect(() => {
    tipTimerRef.current = setTimeout(() => setShowTips(true), TIP_SHOW_DELAY_MS);
    return () => {
      if (tipTimerRef.current) clearTimeout(tipTimerRef.current);
    };
  }, []);

  return (
    <div className="flex flex-col items-center justify-start min-h-[60vh] px-4 pt-20 pb-12">
      {/* Primary panel */}
      <div className="w-full max-w-md space-y-6">
        {/* Radar animation */}
        <div className="flex justify-center">
          <CenterSpinner />
        </div>

        {/* Title */}
        <div className="text-center space-y-1">
          <h2 className="text-lg font-semibold text-[#1F2A44]">
            {title}
          </h2>
          {subtitle && (
            <p className="text-sm text-[#6B7A90] max-w-sm mx-auto">
              {subtitle}
            </p>
          )}
          {goalTitle != null && goalTitle !== '' && (
            <p className="text-xs text-[#6B7A90] truncate max-w-xs mx-auto">
              {goalTitle}
            </p>
          )}
        </div>

        {/* Progress bar */}
        {stepCount > 0 && (
          <div className="w-full space-y-1">
            <div className="h-1.5 w-full rounded-full bg-[#E8F0F7] overflow-hidden">
              <div
                className="h-full rounded-full bg-[#5B8DEF] transition-[width] duration-700 ease-out"
                style={{ width: `${Math.min(95, ((stepIndex + 1) / stepCount) * 90 + 5)}%` }}
              />
            </div>
          </div>
        )}

        {/* Step checklist */}
        {stepCount > 0 && (
          <div className="bg-white border border-[#DCE6F2] rounded-xl px-5 py-4 shadow-sm">
            <StepProgress steps={steps} activeIndex={stepIndex} />
          </div>
        )}
      </div>

      {/* Secondary: tips (delayed) */}
      {tips.length > 0 && (
        <div
          className={cn(
            'w-full max-w-md mt-10 transition-all duration-500',
            showTips ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none',
          )}
        >
          <TipCarousel tips={tips} />
        </div>
      )}
    </div>
  );
}
