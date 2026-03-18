import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Select } from '@/components/ui';
import { cn } from '@/lib/cn';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/context/GoalsContext';
import { useDashboardMetrics } from '@/api/endpoints/content';
import { useBehavioralMetrics } from '@/api/endpoints/metrics';
import { SkillRadarChart, SessionTimeChart, MasteryChart } from '@/components/analytics';

const TIME_OPTIONS = ['Last 7 days', 'Last 30 days', 'All time'] as const;
type TimeRange = (typeof TIME_OPTIONS)[number];


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
  const navigate = useNavigate();

  const { userId } = useAuthContext();
  const { goals, selectedGoalId, setSelectedGoalId } = useGoalsContext();

  const { data: metrics, isLoading: metricsLoading } = useDashboardMetrics(
    userId ?? undefined,
    selectedGoalId ?? undefined,
  );

  const { data: behavioralMetrics, isLoading: behavioralLoading } = useBehavioralMetrics(
    userId ?? undefined,
  );

  const isLoading = metricsLoading || behavioralLoading;

  const activeGoals = goals.filter((g) => !g.is_deleted);

  const totalSessions = behavioralMetrics?.total_sessions_in_path
    ?? activeGoals.reduce((sum, g) => sum + (g.learning_path?.length ?? 0), 0);
  const sessionsCompleted = behavioralMetrics?.sessions_completed
    ?? activeGoals.reduce((sum, g) => sum + (g.learning_path?.filter((s) => s.if_learned).length ?? 0), 0);
  const totalStudyTimeSec = behavioralMetrics?.total_learning_time_sec ?? 0;
  const avgSessionDurationSec = behavioralMetrics?.avg_session_duration_sec ?? 0;

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
        {/* Sessions Completed */}
        <div className="bg-white text-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                Sessions completed
              </p>
              <p className="mt-2 text-2xl font-semibold">
                {isLoading ? (
                  <span className="inline-flex h-6 w-16 rounded bg-slate-200 animate-pulse" />
                ) : (
                  `${sessionsCompleted} / ${totalSessions}`
                )}
              </p>
              <p className="mt-1 text-[11px] text-slate-400">
                Across all active learning goals.
              </p>
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
                  <span className="inline-flex h-6 w-14 rounded bg-slate-200 animate-pulse" />
                ) : (
                  activeGoals.length
                )}
              </p>
              <p className="mt-1 text-[11px] text-slate-400">
                Goals that are not archived or deleted.
              </p>
            </div>        
          </div>
        </div>

        {/* Total Study Time */}
        <div className="bg-white text-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                Total study time
              </p>
              <p className="mt-2 text-2xl font-semibold">
                {isLoading ? (
                  <span className="inline-flex h-6 w-14 rounded bg-slate-200 animate-pulse" />
                ) : totalStudyTimeSec > 0 ? (
                  totalStudyTimeSec >= 3600
                    ? `${(totalStudyTimeSec / 3600).toFixed(1)}h`
                    : `${Math.round(totalStudyTimeSec / 60)}m`
                ) : (
                  '0m'
                )}
              </p>
              <p className="mt-1 text-[11px] text-slate-400">
                {avgSessionDurationSec > 0
                  ? `Avg ${Math.round(avgSessionDurationSec / 60)}m per session`
                  : 'Time spent across all sessions.'}
              </p>
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
                  <span className="inline-flex h-6 w-24 rounded bg-slate-200 animate-pulse" />
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
      
          </div>
        </div>
      </div>

      {/* Goals overview + charts — items-start so left column height fits content */}
      <div className="mt-6 grid grid-cols-1 xl:grid-cols-[minmax(0,2.2fr)_minmax(0,1.5fr)] gap-6 items-start">
        {/* Goals overview list */}
        <section className="bg-white rounded-2xl border border-slate-200 shadow-sm self-start w-full">
          <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">Goals overview</h3>
              <p className="mt-1 text-xs text-slate-500">
                Summary of each goal&apos;s status, progress, and what&apos;s coming next.
              </p>
            </div>
            <p className="hidden md:block text-[11px] text-slate-400">
              Use the arrow to open that goal on Learning Path.
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

                    <button
                      type="button"
                      className="shrink-0 self-start rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-800 transition-colors"
                      aria-label="Open goal on Learning Path"
                      onClick={() => {
                        setSelectedGoalId(goal.id);
                        navigate('/learning-path');
                      }}
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
                    </button>
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
            <p className="text-xs text-slate-500 mb-2">
              Each bar represents how long you spent in a session. Taller bars mean more focused
              study time.
            </p>
            {isLoading && sessionTimeSeries.length === 0 ? (
              <div className="h-[200px] flex items-center justify-center text-[11px] text-slate-400">
                Loading activity…
              </div>
            ) : sessionTimeSeries.length === 0 ? (
              <div className="h-[200px] flex items-center justify-center text-[11px] text-slate-400">
                Complete your first learning session to see activity here.
              </div>
            ) : (
              <SessionTimeChart data={sessionTimeSeries} />
            )}
          </section>

          {/* Overall progress trend (line chart) */}
          <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 sm:p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-slate-900">Overall progress trend</h3>
              <span className="text-[11px] text-slate-400">
                {masterySeries.length > 0 ? 'Mastery by session' : 'No trend yet'}
              </span>
            </div>
            <p className="text-xs text-slate-500 mb-2">
              Track how your mastery percentage changes as you complete more sessions.
            </p>
            {isLoading && masterySeries.length === 0 ? (
              <div className="h-[200px] flex items-center justify-center text-[11px] text-slate-400">
                Loading trend…
              </div>
            ) : masterySeries.length === 0 ? (
              <div className="h-[200px] flex items-center justify-center text-[11px] text-slate-400">
                Once you have mastery data, we will chart it here.
              </div>
            ) : (
              <MasteryChart data={masterySeries} />
            )}
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
  const [timeRange, setTimeRange] = useState<TimeRange>('Last 7 days');
  const { userId } = useAuthContext();
  const { goals, selectedGoalId, setSelectedGoalId } = useGoalsContext();
  const { activeGoal } = useActiveGoal();

  const goalOptions = goals.map((g) => ({
    value: String(g.id),
    label: ((g.learner_profile?.goal_display_name as string | undefined) ?? g.learning_goal).slice(0, 50),
  }));

  const { data: metrics, isLoading: dashLoading } = useDashboardMetrics(userId ?? undefined, activeGoal?.id);
  const { data: behavMetrics, isLoading: behavLoading } = useBehavioralMetrics(userId ?? undefined, activeGoal?.id);
  const isLoading = dashLoading || behavLoading;

  const overallProgress = metrics?.overall_progress ?? 0;
  const goalProgressPct = Math.round((overallProgress ?? 0) * 100);

  const sessionsCompleted = behavMetrics?.sessions_completed
    ?? (activeGoal?.learning_path ?? []).filter(
      (s: { if_learned?: boolean }) => s.if_learned,
    ).length;
  const masterySeries = metrics?.mastery_time_series ?? [];
  const sessionSeries = metrics?.session_time_series ?? [];

  const quizAvgPct =
    behavMetrics?.latest_mastery_rate != null
      ? Math.round(behavMetrics.latest_mastery_rate * 100)
      : masterySeries.length > 0
        ? Math.round(
            masterySeries.reduce((sum, p) => sum + (p.mastery_pct ?? 0), 0) / masterySeries.length,
          )
        : null;

  const totalStudySeconds = behavMetrics?.total_learning_time_sec
    ?? sessionSeries.reduce((sum, s) => sum + (s.duration_sec ?? 0), 0);
  const studyHours = totalStudySeconds / 3600;

  const streakDays = sessionsCompleted;

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

  type SkillTier = 'mastered' | 'current' | 'locked';
  let foundCurrent = false;
  const tieredSkills = skillItems.map((skill) => {
    let tier: SkillTier;
    if (skill.current >= skill.required && skill.required > 0) {
      tier = 'mastered';
    } else if (!foundCurrent) {
      tier = 'current';
      foundCurrent = true;
    } else {
      tier = 'locked';
    }
    return { ...skill, tier };
  });

  const selectedGoalLabel =
    goalOptions.find((g) => g.value === String(selectedGoalId ?? ''))?.label ??
    ((activeGoal?.learner_profile?.goal_display_name as string | undefined) ?? activeGoal?.learning_goal ?? 'Goal');

  return (
    <div className="space-y-6">
      {/* Header: title + goal dropdown + time filter */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
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

      {/* Skill mastery — analytics-focused view */}
      <section className="bg-white rounded-xl border border-slate-200 p-5">
        <h3 className="text-base font-semibold text-slate-800 mb-4">Skill mastery</h3>

        {skillItems.length === 0 && !isLoading ? (
          <p className="text-sm text-slate-500">No skill metrics available yet for this goal.</p>
        ) : (
          <div className="space-y-5">
            {/* 1. Summary stats */}
            {(() => {
              const mastered = tieredSkills.filter((s) => s.tier === 'mastered');
              const currentSkill = tieredSkills.find((s) => s.tier === 'current');
              const started = tieredSkills.filter((s) => s.current > 0);
              return (
                <div className="grid grid-cols-3 gap-4">
                  <div className="rounded-lg bg-slate-50 border border-slate-100 px-4 py-3">
                    <p className="text-xs text-slate-500">Skills started</p>
                    <p className="text-sm font-semibold text-slate-900 mt-1">{started.length} / {tieredSkills.length}</p>
                  </div>
                  <div className="rounded-lg bg-slate-50 border border-slate-100 px-4 py-3">
                    <p className="text-xs text-slate-500">Skills mastered</p>
                    <p className="text-sm font-semibold text-slate-900 mt-1">{mastered.length} / {tieredSkills.length}</p>
                  </div>
                  <div className="rounded-lg bg-slate-50 border border-slate-100 px-4 py-3">
                    <p className="text-xs text-slate-500">Current focus</p>
                    <p className="text-sm font-semibold text-slate-900 mt-1 truncate">{currentSkill?.name ?? '—'}</p>
                  </div>
                </div>
              );
            })()}

            {/* 2. Current focus card */}
            {(() => {
              const currentSkill = tieredSkills.find((s) => s.tier === 'current');
              if (!currentSkill) return null;
              const pct = currentSkill.required > 0
                ? Math.round((currentSkill.current / currentSkill.required) * 100)
                : 0;
              return (
                <div className="rounded-xl border border-primary-200 bg-primary-50/50 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-semibold text-slate-900 truncate">{currentSkill.name}</h4>
                        <span className="shrink-0 text-[11px] font-medium px-2 py-0.5 rounded-full bg-primary-200 text-primary-800">
                          Current
                        </span>
                      </div>
                      <div className="mt-3 flex items-center gap-3">
                        <div className="flex-1 max-w-xs h-2 rounded-full bg-primary-200/60 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-primary-600 transition-all"
                            style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
                          />
                        </div>
                        <span className="text-sm font-medium text-slate-700">{pct}%</span>
                      </div>
                      <p className="text-xs text-slate-500 mt-2">
                        {currentSkill.current}% current / {currentSkill.required}% required
                      </p>
                    </div>
                    <Link
                      to="/learning-session"
                      className="shrink-0 text-xs font-medium text-primary-700 hover:text-primary-900 border border-primary-300 rounded-md px-3 py-1.5 transition-colors hover:bg-primary-100"
                    >
                      View current session
                    </Link>
                  </div>
                </div>
              );
            })()}

            {/* 3. Upcoming journey + Skill Analysis (two-column) */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left: Timeline */}
              <div>
                <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-4">Upcoming journey</h4>
                <div className="relative pl-6">
                  {/* Vertical line */}
                  <div className="absolute left-[9px] top-1 bottom-1 w-px bg-slate-200" />

                  {tieredSkills.filter((s) => s.tier !== 'mastered').map((skill) => {
                    const isCurrent = skill.tier === 'current';
                    return (
                      <div key={skill.id} className={cn('relative pb-6 last:pb-0', !isCurrent && 'opacity-50')}>
                        {/* Node */}
                        <div className={cn(
                          'absolute -left-6 top-0.5 w-[18px] h-[18px] rounded-full border-2 flex items-center justify-center',
                          isCurrent
                            ? 'border-primary-500 bg-primary-500'
                            : 'border-slate-300 bg-white',
                        )}>
                          {isCurrent && (
                            <div className="w-1.5 h-1.5 rounded-full bg-white" />
                          )}
                        </div>

                        {/* Content */}
                        <div>
                          <p className={cn(
                            'text-sm font-semibold',
                            isCurrent ? 'text-slate-900' : 'text-slate-500',
                          )}>
                            {skill.name}
                          </p>
                          <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5">
                            {isCurrent ? (
                              <>In progress — {skill.current}% / {skill.required}%</>
                            ) : (
                              <>
                                <svg className="w-3 h-3 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
                                </svg>
                                Locked until previous session
                              </>
                            )}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Right: Skill Radar */}
              <div>
                <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-4">Skill analysis</h4>
                {radar && radar.labels.length > 0 ? (
                  <SkillRadarChart
                    labels={radar.labels}
                    currentLevels={radar.current_levels}
                    requiredLevels={radar.required_levels}
                  />
                ) : (
                  <div className="h-56 bg-slate-50 rounded-lg border border-dashed border-slate-200 flex items-center justify-center text-slate-400 text-sm">
                    Skill radar will appear once you have skill metrics.
                  </div>
                )}
              </div>
            </div>

            {/* 4. Mastered skills (collapsed chips) */}
            {(() => {
              const mastered = tieredSkills.filter((s) => s.tier === 'mastered');
              if (mastered.length === 0) return null;
              return (
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">Mastered</h4>
                  <div className="flex flex-wrap gap-2">
                    {mastered.map((skill) => (
                      <span
                        key={skill.id}
                        className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600"
                      >
                        <svg className="w-3.5 h-3.5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        {skill.name}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })()}

            {/* 5. Helper text */}
            <p className="text-[11px] text-slate-400 text-center pt-1">
              Progress follows the current learning path.
            </p>
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
            {isLoading && sessionSeries.length === 0 ? (
              <div className="h-60 flex items-center justify-center text-[11px] text-slate-400">
                Loading activity…
              </div>
            ) : sessionSeries.length === 0 ? (
              <div className="h-60 flex items-center justify-center text-[11px] text-slate-400">
                Complete a learning session to see activity here.
              </div>
            ) : (
              <SessionTimeChart data={sessionSeries} />
            )}
          </div>

          {/* Quiz scores (mastery line) */}
          <div className="bg-white rounded-xl border border-slate-200 p-4 flex flex-col">
            <h4 className="text-sm font-semibold text-slate-800 mb-2">Quiz scores</h4>
            <p className="text-xs text-slate-500 mb-3">
              Mastery percentage for recent sessions with quizzes.
            </p>
            {isLoading && masterySeries.length === 0 ? (
              <div className="h-60 flex items-center justify-center text-[11px] text-slate-400">
                Loading scores…
              </div>
            ) : masterySeries.length === 0 ? (
              <div className="h-60 flex items-center justify-center text-[11px] text-slate-400">
                Quiz scores will appear here after you complete quizzes.
              </div>
            ) : (
              <MasteryChart data={masterySeries} />
            )}
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
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 space-y-4">
      <div className="flex justify-start items-center">
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
