import { cn } from '@/lib/cn';
import type { GoalRuntimeStateSession, LearningPathSession } from '@/types';

interface SessionCardProps {
  index: number;
  pathSession: LearningPathSession;
  runtimeSession?: GoalRuntimeStateSession;
  onLaunch: () => void;
  disabled?: boolean;
}

export function SessionCard({ index, pathSession, runtimeSession, onLaunch, disabled }: SessionCardProps) {
  const isLocked = runtimeSession?.is_locked ?? false;
  const canOpen = runtimeSession?.can_open ?? true;
  const ifLearned = runtimeSession?.if_learned ?? false;
  const isMastered = runtimeSession?.is_mastered ?? false;
  const masteryScore = runtimeSession?.mastery_score;
  const masteryPct = masteryScore != null ? Math.round(masteryScore * 100) : null;

  return (
    <div
      className={cn(
        'bg-white rounded-xl border p-5 space-y-3 transition-all',
        isLocked ? 'border-slate-100 opacity-60' : 'border-slate-200 hover:shadow-sm',
        ifLearned && 'border-l-4 border-l-green-400',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-xs font-medium text-slate-400">Session {index + 1}</span>
            {ifLearned && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">
                Completed
              </span>
            )}
            {isMastered && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary-100 text-primary-700 font-medium">
                Mastered
              </span>
            )}
            {isLocked && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
                Locked
              </span>
            )}
          </div>
          <h3 className="font-semibold text-slate-800 leading-snug">
            {(pathSession.title as string | undefined) ?? `Session ${index + 1}`}
          </h3>
          {(pathSession.abstract as string | undefined) && (
            <p className="mt-1 text-sm text-slate-500 leading-relaxed line-clamp-2">
              {pathSession.abstract as string}
            </p>
          )}
          {Array.isArray(pathSession.associated_skills) && pathSession.associated_skills.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {(pathSession.associated_skills as string[]).slice(0, 4).map((skill) => (
                <span key={skill} className="text-xs px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full">
                  {skill}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          {masteryPct != null && (
            <span className="text-xs font-medium text-slate-500">{masteryPct}% mastery</span>
          )}
          <button
            type="button"
            onClick={onLaunch}
            disabled={isLocked || !canOpen || disabled}
            className={cn(
              'px-4 py-2 rounded-lg text-sm font-medium transition-all',
              isLocked || !canOpen || disabled
                ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                : ifLearned
                ? 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                : 'bg-primary-600 text-white hover:bg-primary-700',
            )}
          >
            {isLocked ? 'Locked' : ifLearned ? 'Review' : 'Start'}
          </button>
        </div>
      </div>
    </div>
  );
}
