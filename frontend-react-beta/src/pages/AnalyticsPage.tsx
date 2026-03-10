import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button, Select } from '@/components/ui';
import { cn } from '@/lib/cn';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/context/GoalsContext';
import { useDashboardMetrics } from '@/api/endpoints/content';

/* ------------------------------------------------------------------ */
/*  Mock data                                                         */
/* ------------------------------------------------------------------ */

const TIME_OPTIONS = ['Last 7 days', 'Last 30 days', 'All time'] as const;
type TimeRange = (typeof TIME_OPTIONS)[number];

const GOAL_OPTIONS = [
  { value: 'g1', label: 'Learn French for Travel' },
  { value: 'g2', label: 'Goal Name 2' },
  { value: 'g3', label: 'Goal Name 3' },
];

const OVERVIEW_GOALS = [
  { id: '1', name: '[Goal name]', status: 'In progress' as const, progress: 50, topGap: '[Skills]', nextUp: '[module name]' },
  { id: '2', name: '[Goal name]', status: 'At Risk' as const, progress: 50, topGap: '[Skills]', nextUp: '[module name]' },
  { id: '3', name: '[Goal name]', status: 'In progress' as const, progress: 50, topGap: '[Skills]', nextUp: '[module name]' },
];

const SKILL_MASTERY_FILTERS = ['All', 'Gaps only', 'Mastered'] as const;
const SKILLS = [
  { id: '1', name: '[Skills name]', status: 'In progress' as const, current: 50, required: 80 },
  { id: '2', name: '[Skills name]', status: 'Not Started' as const, current: 10, required: 80 },
  { id: '3', name: '[Skills name]', status: 'Not Started' as const, current: 10, required: 80 },
  { id: '4', name: '[Skills name]', status: 'Completed' as const, current: 80, required: 80 },
];

function ClockIcon() {
  return (
    <svg className="w-5 h-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Overview view (Goals overview)                                    */
/* ------------------------------------------------------------------ */

function AnalyticsOverview() {
  const [timeRange, setTimeRange] = useState<TimeRange>('Last 30 days');

  const { userId } = useAuthContext();
  const { goals } = useGoalsContext();
  const { activeGoal } = useActiveGoal();

  const { data: metrics, isLoading } = useDashboardMetrics(
    userId ?? undefined,
    undefined,
  );

  const activeGoals = goals.filter((g) => !g.is_deleted);
  const totalSessions = metrics?.total_sessions_in_path ?? 0;
  const sessionsCompleted = metrics?.sessions_completed ?? 0;
  const sessionTimeSeries = metrics?.session_time_series ?? [];
  const masterySeries = metrics?.mastery_time_series ?? [];

  // Derive per-goal progress for "At risk" / "Best performing"
  const goalProgress = activeGoals.map((goal) => {
    const lp = (goal.learning_path ?? []) as Array<{ if_learned?: boolean; title?: string }>;
    const total = lp.length;
    const completed = lp.filter((s) => s.if_learned).length;
    const progress = total > 0 ? completed / total : 0;
    const nextSession = lp.find((s) => !s.if_learned);
    const nextUp =
      (nextSession?.title as string | undefined) ??
      (total > 0 ? `Session ${completed + 1}` : '—');
    return { goal, total, completed, progress, nextUp };
  });

  const atRiskGoals = goalProgress.filter((g) => g.total > 0 && g.progress < 0.3);
  const bestGoal =
    goalProgress.reduce(
      (best, g) => (g.progress > (best?.progress ?? -1) ? g : best),
      undefined as (typeof goalProgress)[number] | undefined,
    ) ?? null;

  return (
    <div className="space-y-6">
      {/* Header + time filter */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-800">Learning Analytics</h2>
          <p className="mt-1 text-sm text-slate-500">
            Track your progress, skills, and learning patterns across all goals.
          </p>
        </div>
        <div className="flex gap-2">
          {TIME_OPTIONS.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => setTimeRange(opt)}
              className={cn(
                'text-sm font-medium px-3 py-1.5 rounded-md transition-colors',
                timeRange === opt ? 'bg-primary-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
              )}
            >
              {timeRange === opt ? '✔ ' : ''}{opt}
            </button>
          ))}
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {/* Total Sessions */}
        <div className="bg-white text-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                Total sessions
              </p>
              <p className="mt-2 text-2xl font-semibold">
                {isLoading ? (
                  <span className="inline-flex h-6 w-16 rounded bg-slate-700 animate-pulse" />
                ) : (
                  totalSessions
                )}
              </p>
              <p className="mt-1 text-[11px] text-slate-400">
                Across all active learning goals.
              </p>
            </div>
            <div className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-100">
              <span className="text-lg text-slate-600">📊</span>
            </div>
          </div>
        </div>

        {/* Active Goals */}
        <div className="bg-white text-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                Active goals
              </p>
              <p className="mt-2 text-2xl font-semibold">
                {isLoading ? (
                  <span className="inline-flex h-6 w-14 rounded bg-slate-700 animate-pulse" />
                ) : (
                  activeGoals.length
                )}
              </p>
              <p className="mt-1 text-[11px] text-slate-400">
                Goals that are not archived or deleted.
              </p>
            </div>
            <div className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-100">
              <span className="text-lg text-slate-600">🎯</span>
            </div>
          </div>
        </div>

        {/* At Risk */}
        <div className="bg-white text-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                At risk
              </p>
              <p className="mt-2 text-2xl font-semibold">
                {isLoading ? (
                  <span className="inline-flex h-6 w-14 rounded bg-slate-700 animate-pulse" />
                ) : (
                  atRiskGoals.length
                )}
              </p>
              <p className="mt-1 text-[11px] text-slate-400">
                {atRiskGoals[0]
                  ? (atRiskGoals[0].goal.learning_goal ||
                      (atRiskGoals[0].goal.learner_profile
                        ?.goal_display_name as string | undefined) ||
                      'Unnamed goal')
                  : 'No goals currently flagged.'}
              </p>
            </div>
            <div className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-100">
              <span className="text-lg text-slate-600">⚠️</span>
            </div>
          </div>
        </div>

        {/* Best Performing */}
        <div className="bg-white text-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                Best performing
              </p>
              <p className="mt-2 text-lg font-semibold truncate max-w-[11rem]">
                {isLoading ? (
                  <span className="inline-flex h-6 w-24 rounded bg-slate-700 animate-pulse" />
                ) : bestGoal ? (
                  (bestGoal.goal.learner_profile?.goal_display_name as string | undefined) ??
                  bestGoal.goal.learning_goal ??
                  'Untitled goal'
                ) : (
                  'No data yet'
                )}
              </p>
              <p className="mt-1 text-[11px] text-slate-400">
                {bestGoal
                  ? `${Math.round(bestGoal.progress * 100)}% complete`
                  : 'Complete a few sessions to see this.'}
              </p>
            </div>
            <div className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-100">
              <span className="text-lg text-slate-600">🏆</span>
            </div>
          </div>
        </div>
      </div>

      {/* Goals overview + charts */}
      <div className="mt-6 grid grid-cols-1 xl:grid-cols-[minmax(0,2.2fr)_minmax(0,1.5fr)] gap-6">
        {/* Goals overview list */}
        <section className="bg-white rounded-2xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">Goals overview</h3>
              <p className="mt-1 text-xs text-slate-500">
                Summary of each goal&apos;s status, progress, and what&apos;s coming next.
              </p>
            </div>
            <p className="hidden md:block text-[11px] text-slate-400">
              Click any goal in other pages to dive deeper.
            </p>
          </div>
          <div className="divide-y divide-slate-100">
            {activeGoals.length === 0 && !isLoading && (
              <div className="px-4 sm:px-6 py-8 text-center text-sm text-slate-500">
                No active goals yet. Create a learning goal to see analytics here.
              </div>
            )}

            {isLoading &&
              [1, 2, 3].map((i) => (
                <div key={i} className="px-4 sm:px-6 py-4 flex items-center gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-32 rounded bg-slate-100 animate-pulse" />
                    <div className="h-2 w-full rounded bg-slate-100 animate-pulse" />
                  </div>
                  <div className="h-7 w-20 rounded-full bg-slate-100 animate-pulse" />
                </div>
              ))}

            {!isLoading &&
              goalProgress.map(({ goal, total, completed, progress, nextUp }) => {
                const progressPct = Math.round(progress * 100);
                const statusLabel =
                  progressPct === 100
                    ? 'Completed'
                    : progressPct === 0
                      ? 'In progress'
                      : 'In progress';

                return (
                  <div
                    key={goal.id}
                    className="px-4 sm:px-6 py-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4 hover:bg-slate-50/60 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-900 truncate">
                        {(goal.learner_profile?.goal_display_name as string | undefined) ??
                          goal.learning_goal ??
                          'Untitled goal'}
                      </p>
                      <span
                        className={cn(
                          'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium mt-1',
                          progressPct === 100
                            ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100'
                            : 'bg-slate-50 text-slate-700 ring-1 ring-slate-100',
                        )}
                      >
                        {statusLabel}
                      </span>
                    </div>

                    <div className="w-full sm:w-64 space-y-1">
                      <div className="flex items-center justify-between text-xs text-slate-500">
                        <span>Overall progress</span>
                        <span className="font-medium text-slate-700">{progressPct}%</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-slate-900 transition-all"
                          style={{ width: `${progressPct}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-slate-400 gap-3">
                        <span>
                          {completed} of {total} sessions completed
                        </span>
                        <span className="truncate max-w-[10rem]">
                          Next up:{' '}
                          <span className="text-slate-600">
                            {total === 0 ? 'No learning path yet' : nextUp}
                          </span>
                        </span>
                      </div>
                    </div>

                    <Link
                      to="/analytics"
                      className="shrink-0 self-start text-slate-400 hover:text-slate-700"
                      aria-label="View goal details"
                    >
                      <svg
                        className="w-5 h-5"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M8.25 4.5l7.5 7.5-7.5 7.5"
                        />
                      </svg>
                    </Link>
                  </div>
                );
              })}
          </div>
        </section>

        {/* Right column: activity + trend charts based on real metrics */}
        <div className="space-y-4">
          {/* Learning activity (bar chart) */}
          <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 sm:p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-slate-900">Learning activity</h3>
              <span className="text-[11px] text-slate-400">
                {sessionTimeSeries.length > 0 ? 'Session durations' : 'No activity yet'}
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Each bar represents how long you spent in a session. Taller bars mean more focused
              study time.
            </p>
            <div className="mt-4 h-[140px] rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-3 flex items-end gap-2 overflow-x-auto">
              {isLoading && sessionTimeSeries.length === 0 ? (
                <div className="w-full h-full flex items-center justify-center text-[11px] text-slate-400">
                  Loading activity…
                </div>
              ) : sessionTimeSeries.length === 0 ? (
                <div className="w-full h-full flex items-center justify-center text-[11px] text-slate-400">
                  Complete your first learning session to see activity here.
                </div>
              ) : (
                (() => {
                  const maxDuration = Math.max(
                    ...sessionTimeSeries.map((s) => s.duration_sec || 0),
                  );
                  const safeMax = maxDuration || 1;
                  return sessionTimeSeries.map((entry) => {
                    const heightPct = ((entry.duration_sec || 0) / safeMax) * 100;
                    return (
                      <div
                        key={entry.session_index}
                        className="flex flex-col items-center justify-end gap-1"
                      >
                        <div
                          className="w-6 rounded-full bg-slate-900/80"
                          style={{ height: `${Math.max(heightPct, 8)}%` }}
                        />
                        <span className="text-[10px] text-slate-500">
                          S{entry.session_index + 1}
                        </span>
                      </div>
                    );
                  });
                })()
              )}
            </div>
          </section>

          {/* Overall progress trend (line-like) */}
          <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 sm:p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-slate-900">Overall progress trend</h3>
              <span className="text-[11px] text-slate-400">
                {masterySeries.length > 0 ? 'Mastery by session' : 'No trend yet'}
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Track how your mastery percentage changes as you complete more sessions.
            </p>
            <div className="mt-4 h-[140px] rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-3 flex flex-col justify-between">
              {isLoading && masterySeries.length === 0 ? (
                <div className="w-full h-full flex items-center justify-center text-[11px] text-slate-400">
                  Loading trend…
                </div>
              ) : masterySeries.length === 0 ? (
                <div className="w-full h-full flex items-center justify-center text-[11px] text-slate-400">
                  Once you have mastery data, we will chart it here.
                </div>
              ) : (
                <>
                  <div className="flex-1 flex items-end gap-3">
                    {masterySeries.map((point, idx) => {
                      const pct = point.mastery_pct ?? 0;
                      return (
                        <div
                          key={idx}
                          className="flex-1 flex flex-col items-center gap-1 min-w-[1.75rem]"
                        >
                          <div className="relative h-20 w-full">
                            <div className="absolute inset-x-0 bottom-0 h-px bg-slate-200" />
                            <div
                              className="absolute bottom-0 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-slate-900"
                              style={{ bottom: `${(pct / 100) * 100}%` }}
                            />
                          </div>
                          <span className="text-[10px] text-slate-500">
                            S{point.session_index + 1}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  <div className="mt-1 flex justify-between text-[10px] text-slate-400">
                    <span>Lower mastery</span>
                    <span>Higher mastery</span>
                  </div>
                </>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Active Goal view                                                   */
/* ------------------------------------------------------------------ */

function AnalyticsActiveGoal() {
  const navigate = useNavigate();
  const [timeRange, setTimeRange] = useState<TimeRange>('Last 7 days');
  const [skillFilter, setSkillFilter] = useState<(typeof SKILL_MASTERY_FILTERS)[number]>('All');

  const { userId } = useAuthContext();
  const { goals, selectedGoalId, setSelectedGoalId } = useGoalsContext();
  const { activeGoal } = useActiveGoal();

  const goalOptions = goals.map((g) => ({
    value: String(g.id),
    label: ((g.learner_profile?.goal_display_name as string | undefined) ?? g.learning_goal).slice(0, 50),
  }));

  const { data: metrics, isLoading } = useDashboardMetrics(userId ?? undefined, activeGoal?.id);

  const overallProgress = metrics?.overall_progress ?? 0;
  const goalProgressPct = Math.round((overallProgress ?? 0) * 100);

  const sessionsCompleted = (activeGoal?.learning_path ?? []).filter(
    (s: { if_learned?: boolean }) => s.if_learned,
  ).length;
  const totalSessions = activeGoal?.learning_path?.length ?? 0;

  const masterySeries = metrics?.mastery_time_series ?? [];
  const sessionSeries = metrics?.session_time_series ?? [];

  const quizAvgPct =
    masterySeries.length > 0
      ? Math.round(
          masterySeries.reduce((sum, p) => sum + (p.mastery_pct ?? 0), 0) / masterySeries.length,
        )
      : null;

  const totalStudySeconds = sessionSeries.reduce(
    (sum, s) => sum + (s.duration_sec ?? 0),
    0,
  );
  const studyHours = totalStudySeconds / 3600;

  const streakDays = sessionSeries.length;

  const radar = metrics?.skill_radar;
  const skillItems =
    radar && radar.labels
      ? radar.labels.map((label, idx) => ({
          id: `${label}-${idx}`,
          name: label,
          current: radar.current_levels[idx] ?? 0,
          required: radar.required_levels[idx] ?? 0,
        }))
      : [];

  const filteredSkills = skillItems.filter((skill) => {
    if (skillFilter === 'Gaps only') {
      return skill.current < skill.required;
    }
    if (skillFilter === 'Mastered') {
      return skill.current >= skill.required && skill.required > 0;
    }
    return true;
  });
  const selectedGoalLabel =
    goalOptions.find((g) => g.value === String(selectedGoalId ?? ''))?.label ??
    ((activeGoal?.learner_profile?.goal_display_name as string | undefined) ?? activeGoal?.learning_goal ?? 'Goal');

  return (
    <div className="space-y-6">
      {/* Header: title + goal dropdown + time filter */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            to="/analytics"
            className="text-sm text-slate-500 hover:text-slate-700 flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
            Overview
          </Link>
          <h2 className="text-lg font-semibold text-slate-800">
            Learning Analytics <span className="text-slate-500 font-normal">[{selectedGoalLabel}]</span>
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {goalOptions.length > 1 && (
            <div className="w-44">
              <Select
                options={goalOptions}
                value={String(selectedGoalId ?? '')}
                onChange={(e) => setSelectedGoalId(Number(e.target.value))}
                aria-label="Select goal"
                className="text-sm"
              />
            </div>
          )}
          <div className="flex gap-2">
            {TIME_OPTIONS.map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => setTimeRange(opt)}
                className={cn(
                  'text-sm font-medium px-3 py-1.5 rounded-md transition-colors',
                  timeRange === opt ? 'bg-primary-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                )}
              >
                {timeRange === opt ? '✔ ' : ''}{opt}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {/* Goal progress */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
          <ClockIcon />
          <p className="text-sm font-semibold text-slate-800 mt-2">Goal progress</p>
          <p className="text-xl font-bold text-slate-900 mt-0.5">
            {isLoading ? (
              <span className="inline-flex h-6 w-16 rounded bg-slate-100 animate-pulse" />
            ) : (
              `${goalProgressPct}%`
            )}
          </p>
          <p className="text-xs text-slate-500 mt-1">How far you are in this learning path.</p>
        </div>

        {/* Quiz score avg */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
          <ClockIcon />
          <p className="text-sm font-semibold text-slate-800 mt-2">Quiz score avg</p>
          <p className="text-xl font-bold text-slate-900 mt-0.5">
            {isLoading ? (
              <span className="inline-flex h-6 w-16 rounded bg-slate-100 animate-pulse" />
            ) : quizAvgPct != null ? (
              `${quizAvgPct}%`
            ) : (
              '—'
            )}
          </p>
          <p className="text-xs text-slate-500 mt-1">Average mastery percentage across sessions.</p>
        </div>

        {/* Study time */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
          <ClockIcon />
          <p className="text-sm font-semibold text-slate-800 mt-2">Study time</p>
          <p className="text-xl font-bold text-slate-900 mt-0.5">
            {isLoading ? (
              <span className="inline-flex h-6 w-20 rounded bg-slate-100 animate-pulse" />
            ) : studyHours > 0 ? (
              `${studyHours.toFixed(1)}h`
            ) : (
              '0h'
            )}
          </p>
          <p className="text-xs text-slate-500 mt-1">Total time recorded for this goal.</p>
        </div>

        {/* Streak */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
          <ClockIcon />
          <p className="text-sm font-semibold text-slate-800 mt-2">Streak</p>
          <p className="text-xl font-bold text-slate-900 mt-0.5">
            {isLoading ? (
              <span className="inline-flex h-6 w-16 rounded bg-slate-100 animate-pulse" />
            ) : (
              `${streakDays} days`
            )}
          </p>
          <p className="text-xs text-slate-500 mt-1">Number of sessions logged for this goal.</p>
        </div>
      </div>

      {/* Skill mastery (from real skill_radar) */}
      <section className="bg-white rounded-xl border border-slate-200 p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-4">
          <h3 className="text-base font-semibold text-slate-800">Skill mastery</h3>
          <div className="flex gap-2">
            {SKILL_MASTERY_FILTERS.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setSkillFilter(f)}
                className={cn(
                  'text-sm font-medium px-3 py-1.5 rounded-md transition-colors',
                  skillFilter === f ? 'bg-primary-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                )}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        {skillItems.length === 0 && !isLoading ? (
          <p className="text-sm text-slate-500">No skill metrics available yet for this goal.</p>
        ) : (
          <ul className="space-y-3">
            {filteredSkills.map((skill) => {
              const progressPct =
                skill.required > 0 ? Math.round((skill.current / skill.required) * 100) : 0;
              const statusLabel =
                skill.current >= skill.required && skill.required > 0
                  ? 'Mastered'
                  : skill.current > 0
                    ? 'In progress'
                    : 'Not started';

              return (
                <li
                  key={skill.id}
                  className="flex flex-col sm:flex-row sm:items-center gap-3 py-3 border-b border-slate-100 last:border-0"
                >
                  <span className="font-medium text-slate-900 sm:w-40">{skill.name}</span>
                  <span
                    className={cn(
                      'text-xs font-medium px-2 py-0.5 rounded-full w-fit',
                      statusLabel === 'In progress' && 'bg-slate-100 text-slate-700',
                      statusLabel === 'Not started' && 'bg-slate-100 text-slate-600',
                      statusLabel === 'Mastered' && 'bg-slate-200 text-slate-800',
                    )}
                  >
                    {statusLabel}
                  </span>
                  <div className="flex-1 flex items-center gap-2">
                    <span className="text-sm text-slate-500 w-24 shrink-0">Mastery</span>
                    <div className="flex-1 max-w-xs h-2 rounded-full bg-slate-200 overflow-hidden">
                      <div
                        className="h-full bg-primary-500 rounded-full transition-all"
                        style={{ width: `${Math.max(0, Math.min(100, progressPct))}%` }}
                      />
                    </div>
                    <span className="text-sm text-slate-600 whitespace-nowrap">
                      {skill.current}% / {skill.required}% required
                    </span>
                  </div>
                  <Button variant="secondary" size="sm">
                    Practice
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Skill Radar (data-aware placeholder) */}
      <section className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-base font-semibold text-slate-800 mb-4">Skill Radar</h3>
        {radar && radar.labels.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] gap-4 items-center">
            <div className="h-56 bg-slate-50 rounded-lg border border-slate-200 flex items-center justify-center text-slate-400 text-xs">
              Simple radar-style visualization can be added later.
            </div>
            <ul className="space-y-2 text-xs text-slate-600">
              {skillItems.map((skill) => {
                const gap = Math.max(0, (skill.required ?? 0) - (skill.current ?? 0));
                return (
                  <li key={skill.id} className="flex items-center justify-between gap-3">
                    <span className="font-medium text-slate-800">{skill.name}</span>
                    <span>
                      {skill.current}% / {skill.required}% required
                      {gap > 0 && <span className="text-amber-600 ml-1">(-{gap} gap)</span>}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : (
          <div className="h-56 bg-slate-50 rounded-lg border border-dashed border-slate-200 flex items-center justify-center text-slate-400 text-sm">
            Skill radar will appear here once you have skill metrics.
          </div>
        )}
      </section>

      {/* Activity + quiz score charts */}
      <section>
        <h3 className="text-base font-semibold text-slate-800 mb-4">Activity & quiz performance</h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Activity this week (sessions bar chart) */}
          <div className="bg-white rounded-xl border border-slate-200 p-4 flex flex-col">
            <h4 className="text-sm font-semibold text-slate-800 mb-2">Activity (sessions)</h4>
            <p className="text-xs text-slate-500 mb-3">
              Bars show how long each session lasted for this goal.
            </p>
            <div className="flex-1 h-40 rounded-lg bg-slate-50 border border-slate-100 px-3 py-3 flex items-end gap-2 overflow-x-auto">
              {isLoading && sessionSeries.length === 0 ? (
                <div className="w-full h-full flex items-center justify-center text-[11px] text-slate-400">
                  Loading activity…
                </div>
              ) : sessionSeries.length === 0 ? (
                <div className="w-full h-full flex items-center justify-center text-[11px] text-slate-400">
                  Complete a learning session to see activity here.
                </div>
              ) : (
                (() => {
                  const maxDuration = Math.max(
                    ...sessionSeries.map((s) => s.duration_sec || 0),
                  );
                  const safeMax = maxDuration || 1;
                  return sessionSeries.map((entry) => {
                    const heightPct = ((entry.duration_sec || 0) / safeMax) * 100;
                    return (
                      <div
                        key={entry.session_index}
                        className="flex flex-col items-center justify-end gap-1"
                      >
                        <div
                          className="w-6 rounded-full bg-slate-900/80"
                          style={{ height: `${Math.max(heightPct, 8)}%` }}
                        />
                        <span className="text-[10px] text-slate-500">
                          S{entry.session_index + 1}
                        </span>
                      </div>
                    );
                  });
                })()
              )}
            </div>
          </div>

          {/* Quiz scores (mastery line) */}
          <div className="bg-white rounded-xl border border-slate-200 p-4 flex flex-col">
            <h4 className="text-sm font-semibold text-slate-800 mb-2">Quiz scores</h4>
            <p className="text-xs text-slate-500 mb-3">
              Mastery percentage for recent sessions with quizzes.
            </p>
            <div className="flex-1 h-40 rounded-lg bg-slate-50 border border-slate-100 px-4 py-3 flex flex-col justify-between">
              {isLoading && masterySeries.length === 0 ? (
                <div className="w-full h-full flex items-center justify-center text-[11px] text-slate-400">
                  Loading scores…
                </div>
              ) : masterySeries.length === 0 ? (
                <div className="w-full h-full flex items-center justify-center text-[11px] text-slate-400">
                  Quiz scores will appear here after you complete quizzes.
                </div>
              ) : (
                <>
                  <div className="flex-1 flex items-end gap-3">
                    {masterySeries.map((point, idx) => {
                      const pct = point.mastery_pct ?? 0;
                      return (
                        <div
                          key={idx}
                          className="flex-1 flex flex-col items-center gap-1 min-w-[1.75rem]"
                        >
                          <div className="relative h-20 w-full">
                            <div className="absolute inset-x-0 bottom-0 h-px bg-slate-200" />
                            <div
                              className="absolute bottom-0 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-slate-900"
                              style={{ bottom: `${(pct / 100) * 100}%` }}
                            />
                          </div>
                          <span className="text-[10px] text-slate-500">
                            S{point.session_index + 1}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  <div className="mt-1 flex justify-between text-[10px] text-slate-400">
                    <span>Lower mastery</span>
                    <span>Higher mastery</span>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export function AnalyticsPage() {
  const [view, setView] = useState<'overview' | 'active-goal'>('overview');

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <div className="flex justify-end">
        <div className="inline-flex rounded-full bg-slate-100 p-1 text-sm font-medium">
          <button
            type="button"
            onClick={() => setView('overview')}
            className={cn(
              'px-3 py-1.5 rounded-full transition-colors',
              view === 'overview' ? 'bg-white shadow text-slate-900' : 'text-slate-600',
            )}
          >
            Overview
          </button>
          <button
            type="button"
            onClick={() => setView('active-goal')}
            className={cn(
              'px-3 py-1.5 rounded-full transition-colors',
              view === 'active-goal' ? 'bg-white shadow text-slate-900' : 'text-slate-600',
            )}
          >
            Active Goal
          </button>
        </div>
      </div>

      {view === 'overview' ? <AnalyticsOverview /> : <AnalyticsActiveGoal />}
    </div>
  );
}
