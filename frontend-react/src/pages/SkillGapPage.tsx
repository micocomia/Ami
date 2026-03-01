import { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Toggle } from '@/components/ui';
import { cn } from '@/lib/cn';

/* ------------------------------------------------------------------ */
/*  Types & constants                                                 */
/* ------------------------------------------------------------------ */

const LEVELS = ['Unlearned', 'Beginner', 'Intermediate', 'Advanced'] as const;
type LevelIndex = 0 | 1 | 2 | 3;

interface SkillGap {
  id: string;
  name: string;
  currentLevel: LevelIndex;
  targetLevel: LevelIndex;
  addToPlan: boolean;
}

type PageState = 'loading' | 'idle' | 'adjusted' | 'submitting';

/* ------------------------------------------------------------------ */
/*  Mock data                                                         */
/* ------------------------------------------------------------------ */

const MOCK_SUBJECT = 'French';

const INITIAL_SKILLS: SkillGap[] = [
  { id: 'comprehension', name: 'French comprehension',           currentLevel: 0, targetLevel: 1, addToPlan: true },
  { id: 'oral',          name: 'French oral expression',         currentLevel: 0, targetLevel: 1, addToPlan: true },
  { id: 'listening',     name: 'French listening comprehension', currentLevel: 1, targetLevel: 3, addToPlan: true },
];

/* ------------------------------------------------------------------ */
/*  Sub-component: LevelTrack                                        */
/* ------------------------------------------------------------------ */

function LevelTrack({
  label,
  level,
  variant,
  onLevelChange,
  disabled,
}: {
  label: string;
  level: LevelIndex;
  variant: 'target' | 'current';
  onLevelChange?: (next: LevelIndex) => void;
  disabled?: boolean;
}) {
  const pct = (level / (LEVELS.length - 1)) * 100;
  const interactive = !!onLevelChange && !disabled;

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-slate-500 w-12 shrink-0">{label}</span>

      <div className="relative flex-1 h-7 flex items-center">
        {/* Rail */}
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-1.5 rounded-full bg-slate-200" />
        {/* Filled bar */}
        <div
          className={cn(
            'absolute top-1/2 -translate-y-1/2 left-0 h-1.5 rounded-full transition-all duration-150',
            variant === 'target' ? 'bg-primary-500' : 'bg-primary-300',
          )}
          style={{ width: `${pct}%` }}
        />
        {/* Level markers — clickable buttons */}
        {LEVELS.map((levelName, i) => {
          const x = (i / (LEVELS.length - 1)) * 100;
          const isActive = i <= level;
          const isSelected = i === level;

          return (
            <button
              key={i}
              type="button"
              disabled={!interactive}
              onClick={() => onLevelChange?.(i as LevelIndex)}
              title={interactive ? `Set to ${levelName}` : levelName}
              className={cn(
                'absolute top-1/2 -translate-y-1/2 -translate-x-1/2',
                'flex items-center justify-center rounded-full transition-transform duration-100',
                interactive
                  ? 'hover:scale-125 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-offset-1 cursor-pointer'
                  : 'cursor-default',
                isSelected && interactive && 'scale-110',
              )}
              style={{ left: `${x}%` }}
            >
              {variant === 'target' ? (
                <svg
                  className={cn(
                    'w-4 h-4 transition-colors',
                    isActive ? 'text-primary-600' : 'text-slate-300',
                    interactive && !isActive && 'hover:text-primary-400',
                  )}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 21V3l9 4.5L21 3v18l-9-4.5L3 21z" />
                </svg>
              ) : (
                <svg
                  className={cn(
                    'w-4 h-4 transition-colors',
                    isActive ? 'text-primary-600' : 'text-slate-300',
                    interactive && !isActive && 'hover:text-primary-400',
                  )}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
                </svg>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Sub-component: LevelLabels                                       */
/* ------------------------------------------------------------------ */

function LevelLabels() {
  return (
    <div className="flex items-center gap-3">
      <span className="w-12 shrink-0" />
      <div className="relative flex-1 flex justify-between">
        {LEVELS.map((l) => (
          <span key={l} className="text-[10px] text-slate-400">{l}</span>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Sub-component: SkillCard                                         */
/* ------------------------------------------------------------------ */

function SkillCard({
  skill,
  onToggle,
  onTargetChange,
  onCurrentChange,
  disabled,
}: {
  skill: SkillGap;
  onToggle: (id: string) => void;
  onTargetChange: (id: string, level: LevelIndex) => void;
  onCurrentChange: (id: string, level: LevelIndex) => void;
  disabled: boolean;
}) {
  const gap = Math.max(0, skill.targetLevel - skill.currentLevel);

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <h3 className="font-semibold text-slate-800">{skill.name}</h3>
        <span
          className={cn(
            'inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full',
            gap >= 2
              ? 'bg-slate-100 text-slate-700'
              : 'bg-slate-100 text-slate-600',
          )}
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
          </svg>
          Gap: {gap} Level
        </span>
      </div>

      {/* Tracks */}
      <div className="px-5 space-y-1.5">
        <LevelTrack
          label="Target"
          level={skill.targetLevel}
          variant="target"
          onLevelChange={(l) => onTargetChange(skill.id, l)}
          disabled={disabled}
        />
        <LevelTrack
          label="Current"
          level={skill.currentLevel}
          variant="current"
          onLevelChange={(l) => onCurrentChange(skill.id, l)}
          disabled={disabled}
        />
        <LevelLabels />
      </div>

      {/* Footer */}
      <div className="flex items-center justify-end gap-4 px-5 py-3 mt-2 border-t border-slate-100">
        <Toggle
          label={skill.addToPlan ? 'Add to Plan' : 'Ignore'}
          checked={skill.addToPlan}
          onChange={() => onToggle(skill.id)}
          disabled={disabled}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page component                                                    */
/* ------------------------------------------------------------------ */

export function SkillGapPage() {
  const navigate = useNavigate();
  const [skills, setSkills] = useState<SkillGap[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [hasAdjusted, setHasAdjusted] = useState(false);

  const pageState: PageState = isLoading
    ? 'loading'
    : isSubmitting
      ? 'submitting'
      : hasAdjusted
        ? 'adjusted'
        : 'idle';

  useEffect(() => {
    const timer = setTimeout(() => {
      setSkills(INITIAL_SKILLS);
      setIsLoading(false);
    }, 1200);
    return () => clearTimeout(timer);
  }, []);

  const handleToggle = useCallback((id: string) => {
    setSkills((prev) =>
      prev.map((s) => (s.id === id ? { ...s, addToPlan: !s.addToPlan } : s)),
    );
    setHasAdjusted(true);
  }, []);

  const handleTargetChange = useCallback((id: string, level: LevelIndex) => {
    setSkills((prev) =>
      prev.map((s) => (s.id === id ? { ...s, targetLevel: level } : s)),
    );
    setHasAdjusted(true);
  }, []);

  const handleCurrentChange = useCallback((id: string, level: LevelIndex) => {
    setSkills((prev) =>
      prev.map((s) => (s.id === id ? { ...s, currentLevel: level } : s)),
    );
    setHasAdjusted(true);
  }, []);

  const handleConfirm = useCallback(() => {
    setIsSubmitting(true);
    setTimeout(() => {
      navigate('/learning-session');
    }, 1500);
  }, [navigate]);

  /* ── Loading skeleton ── */
  if (isLoading) {
    return (
      <div className="max-w-3xl space-y-6">
        <div className="h-6 w-3/4 bg-slate-200 rounded animate-pulse" />
        <div className="h-4 w-1/2 bg-slate-100 rounded animate-pulse" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
            <div className="flex justify-between">
              <div className="h-5 w-48 bg-slate-200 rounded animate-pulse" />
              <div className="h-5 w-24 bg-slate-100 rounded-full animate-pulse" />
            </div>
            <div className="h-8 bg-slate-100 rounded animate-pulse" />
            <div className="h-8 bg-slate-100 rounded animate-pulse" />
          </div>
        ))}
        <p className="text-xs text-slate-400">
          Current state: <code className="bg-slate-100 px-1.5 py-0.5 rounded text-slate-600">loading</code>
        </p>
      </div>
    );
  }

  const plannedCount = skills.filter((s) => s.addToPlan).length;

  return (
    <div className="max-w-3xl space-y-6">
      {/* Intro text */}
      <p className="text-base text-slate-600 leading-relaxed">
        Before beginning, we would like you to assess your current knowledge of{' '}
        <strong className="text-slate-900">{MOCK_SUBJECT}</strong>, to help us
        provide content that suits you the best
      </p>

      {/* Skill cards */}
      <div className="space-y-4">
        {skills.map((skill) => (
          <SkillCard
            key={skill.id}
            skill={skill}
            onToggle={handleToggle}
            onTargetChange={handleTargetChange}
            onCurrentChange={handleCurrentChange}
            disabled={isSubmitting}
          />
        ))}
      </div>

      {/* Bottom action bar */}
      <div className="flex items-center justify-center gap-4 pt-4 pb-8">
        <Button
          variant="secondary"
          size="lg"
          disabled={isSubmitting}
          className="!bg-primary-600 !text-white hover:!bg-primary-700 px-8"
          onClick={() => navigate('/learning-session')}
        >
          Skip
        </Button>
        <Button
          size="lg"
          onClick={handleConfirm}
          loading={isSubmitting}
          disabled={plannedCount === 0}
          className="px-8"
        >
          Confirm and GeneratePath
        </Button>
      </div>

      {/* State indicator */}
      <p className="text-xs text-slate-400">
        Current state: <code className="bg-slate-100 px-1.5 py-0.5 rounded text-slate-600">{pageState}</code>
        {hasAdjusted && <span className="ml-2">({plannedCount} of {skills.length} added to plan)</span>}
      </p>
    </div>
  );
}
