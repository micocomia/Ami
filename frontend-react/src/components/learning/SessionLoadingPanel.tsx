import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/cn';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const ASSISTANT_MESSAGES = [
  'Analyzing your recent learning activity…',
  'Identifying the most relevant knowledge gaps…',
  'Matching the right difficulty for your next session…',
  'Preparing personalized practice content…',
  'Almost ready…',
];

const LOADING_STEPS = [
  'Analyze learning history',
  'Identify knowledge gaps',
  'Match difficulty level',
  'Generate personalized practice',
  'Prepare supporting resources',
];

const LEARNING_TIPS = [
  'Short, frequent review sessions usually work better than one long session.',
  'Practice the hardest items first when your attention is highest.',
  'Mixing reading, listening, and recall improves retention.',
  'Repeating a concept in different contexts strengthens memory.',
  'Small daily progress is usually better than occasional cramming.',
];

const MSG_INTERVAL_MS = 4_500;
const TIP_INTERVAL_MS = 6_000;
const TIP_SHOW_DELAY_MS = 4_000;
const PROGRESS_TICK_MS = 400;

/* ------------------------------------------------------------------ */
/*  Simulated progress curve                                           */
/* ------------------------------------------------------------------ */

function progressAt(elapsedMs: number): number {
  const secs = elapsedMs / 1000;
  // Fast rise to ~60 % in the first 15 s, then gradually approach 88 %.
  // Formula: 88 * (1 - e^(-t/k))  with k chosen so 15 s ≈ 60 %.
  const k = 18;
  return Math.min(88, 88 * (1 - Math.exp(-secs / k)));
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
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

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="w-full space-y-1.5">
      <div className="flex items-center justify-between text-xs text-[#6B7A90]">
        <span>Progress</span>
        <span>{Math.round(value)}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-[#E8F0F7] overflow-hidden">
        <div
          className="h-full rounded-full bg-[#5B8DEF] transition-[width] duration-500 ease-out"
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

function StepChecklist({ progress }: { progress: number }) {
  const completedCount = Math.floor((progress / 100) * LOADING_STEPS.length);

  return (
    <ul className="space-y-2">
      {LOADING_STEPS.map((step, i) => {
        const done = i < completedCount;
        const active = i === completedCount;
        return (
          <li key={step} className="flex items-center gap-2.5 text-sm">
            {done ? (
              <svg
                className="w-4 h-4 text-teal-500 shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            ) : active ? (
              <div className="w-4 h-4 shrink-0 flex items-center justify-center">
                <div className="w-3 h-3 rounded-full border-2 border-[#5B8DEF] border-t-transparent animate-spin" />
              </div>
            ) : (
              <div className="w-4 h-4 shrink-0 flex items-center justify-center">
                <div className="w-2 h-2 rounded-full bg-[#D0DEEF]" />
              </div>
            )}
            <span className={cn(
              done && 'text-teal-700',
              active && 'text-[#1F2A44] font-medium',
              !done && !active && 'text-[#A2B3CC]',
            )}>
              {step}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function RotatingMessage({ messages, intervalMs }: { messages: string[]; intervalMs: number }) {
  const [idx, setIdx] = useState(0);
  const [fadeIn, setFadeIn] = useState(true);

  useEffect(() => {
    const id = setInterval(() => {
      setFadeIn(false);
      setTimeout(() => {
        setIdx((prev) => (prev + 1) % messages.length);
        setFadeIn(true);
      }, 250);
    }, intervalMs);
    return () => clearInterval(id);
  }, [messages.length, intervalMs]);

  return (
    <p
      className={cn(
        'text-sm text-[#6B7A90] transition-opacity duration-250',
        fadeIn ? 'opacity-100' : 'opacity-0',
      )}
    >
      {messages[idx]}
    </p>
  );
}

function LearningTipsCarousel() {
  const [idx, setIdx] = useState(0);
  const [fadeIn, setFadeIn] = useState(true);

  useEffect(() => {
    const id = setInterval(() => {
      setFadeIn(false);
      setTimeout(() => {
        setIdx((prev) => (prev + 1) % LEARNING_TIPS.length);
        setFadeIn(true);
      }, 250);
    }, TIP_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="rounded-xl border border-[#DCE6F2] bg-[#F3F7FB] px-5 py-4 text-center">
      <p className="text-xs font-medium uppercase tracking-wider text-[#6B7A90] mb-2">
        Learning tip
      </p>
      <p
        className={cn(
          'text-sm text-[#4A5975] leading-relaxed transition-opacity duration-250',
          fadeIn ? 'opacity-100' : 'opacity-0',
        )}
      >
        {LEARNING_TIPS[idx]}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

interface SessionLoadingPanelProps {
  sessionTitle: string;
  /** When true, the real data has arrived — snap progress to 100 %. */
  isResolving?: boolean;
}

export function SessionLoadingPanel({ sessionTitle, isResolving }: SessionLoadingPanelProps) {
  const [progress, setProgress] = useState(0);
  const [showTips, setShowTips] = useState(false);
  const startRef = useRef(Date.now());
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const tipTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Simulated progress ticker
  useEffect(() => {
    if (isResolving) {
      setProgress(100);
      if (tickRef.current) clearInterval(tickRef.current);
      return;
    }

    startRef.current = Date.now();
    tickRef.current = setInterval(() => {
      setProgress(progressAt(Date.now() - startRef.current));
    }, PROGRESS_TICK_MS);

    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
    };
  }, [isResolving]);

  // Delayed tips appearance
  useEffect(() => {
    tipTimerRef.current = setTimeout(() => setShowTips(true), TIP_SHOW_DELAY_MS);
    return () => {
      if (tipTimerRef.current) clearTimeout(tipTimerRef.current);
    };
  }, []);

  return (
    <div className="flex flex-col items-center justify-start min-h-[70vh] px-4 pt-20 pb-12 mx-auto">
      {/* Primary loading panel */}
      <div className="w-full max-w-md space-y-6">
        {/* Center spinner */}
        <div className="flex justify-center">
          <CenterSpinner />
        </div>

        {/* Header */}
        <div className="text-center space-y-1">
          <h2 className="text-lg font-semibold text-[#1F2A44]">
            Preparing your session
          </h2>
          <p className="text-xs text-[#6B7A90] truncate max-w-xs mx-auto">
            {sessionTitle}
          </p>
        </div>

        {/* Progress bar */}
        <ProgressBar value={progress} />

        {/* Rotating assistant message */}
        <div className="text-center min-h-[1.5rem]">
          <RotatingMessage messages={ASSISTANT_MESSAGES} intervalMs={MSG_INTERVAL_MS} />
        </div>

        {/* Step checklist */}
        <div className="bg-white border border-[#DCE6F2] rounded-xl px-5 py-4 shadow-sm">
          <StepChecklist progress={progress} />
        </div>
      </div>

      {/* Secondary: learning tips (delayed) */}
      <div
        className={cn(
          'w-full max-w-md mt-10 transition-all duration-500',
          showTips ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none',
        )}
      >
        <LearningTipsCarousel />
      </div>
    </div>
  );
}
