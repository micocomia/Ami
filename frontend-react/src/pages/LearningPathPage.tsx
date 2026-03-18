import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui';
import { SessionCard } from '@/components/learning/SessionCard';
import { PathGenerationLoading } from '@/components/learning/PathGenerationLoading';
import { cn } from '@/lib/cn';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/context/GoalsContext';
import { useAppConfig } from '@/api/endpoints/config';
import { useGoalRuntimeState, patchGoalApi } from '@/api/endpoints/goals';
import { scheduleLearningPathAgenticApi, adaptLearningPathApi } from '@/api/endpoints/learningPath';
import { sessionActivityApi } from '@/api/endpoints/content';

const LEARNING_PATH_LOADING = {
  title: 'Building your learning path',
  steps: [
    'Analyzing your skill gaps...',
    'Reviewing weak knowledge areas...',
    'Matching the right difficulty level...',
    'Building your personalized learning path...',
    'Finalizing your next best steps...',
  ],
  tips: [
    'Short, frequent review sessions usually work better than one long session.',
    'Practice the hardest items first when your attention is highest.',
    'Mixing reading, listening, and recall improves retention.',
    'Repeating a concept in different contexts strengthens memory.',
    'Small daily progress is usually better than occasional cramming.',
    'Teaching what you learn to someone else deepens understanding.',
    'Taking breaks between study blocks boosts long-term recall.',
  ],
} as const;

export function LearningPathPage() {
  const navigate = useNavigate();
  const { userId } = useAuthContext();
  const { goals, selectedGoalId, setSelectedGoalId, refreshGoals, updateGoal, isLoading: goalsLoading } =
    useGoalsContext();
  const { data: config } = useAppConfig();
  const { activeGoal } = useActiveGoal();

  const [isScheduling, setIsScheduling] = useState(false);
  const [isAdapting, setIsAdapting] = useState(false);
  // const [isDesignBiasExpanded, setIsDesignBiasExpanded] = useState(false);
  const [scheduleError, setScheduleError] = useState<string | null>(null);

  const { data: runtimeState, refetch: refetchRuntime } = useGoalRuntimeState(
    userId ?? undefined,
    activeGoal?.id,
  );

  const hasScheduledRef = useRef(false);
  const hasAdaptedRef = useRef<number | null>(null);

  // Auto-schedule if no learning path
  useEffect(() => {
    if (!userId || !activeGoal || !config) return;
    if (activeGoal.learning_path && activeGoal.learning_path.length > 0) return;
    if (hasScheduledRef.current) return;
    hasScheduledRef.current = true;

    setIsScheduling(true);
    setScheduleError(null);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120_000);

    scheduleLearningPathAgenticApi({
      learner_profile: JSON.stringify(activeGoal.learner_profile ?? {}),
    })
      .then(async (result) => {
        clearTimeout(timeoutId);
        if (!userId || !activeGoal) return;
        const updatedGoal = await patchGoalApi(userId, activeGoal.id, {
          learning_path: result.learning_path,
          plan_agent_metadata: result.agent_metadata,
        });
        updateGoal(activeGoal.id, updatedGoal);
        void refetchRuntime();
      })
      .catch((err) => {
        clearTimeout(timeoutId);
        if ((err as Error)?.name !== 'AbortError') {
          setScheduleError('Failed to schedule your learning path. Please try again.');
        }
      })
      .finally(() => setIsScheduling(false));

    return () => {
      clearTimeout(timeoutId);
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, activeGoal?.id, !!config]);

  // Auto-adapt if suggested
  useEffect(() => {
    if (!userId || !activeGoal || !runtimeState) return;
    if (!runtimeState.adaptation?.suggested) return;
    if (hasAdaptedRef.current === activeGoal.id) return;
    hasAdaptedRef.current = activeGoal.id;

    setIsAdapting(true);
    adaptLearningPathApi({
      user_id: userId,
      goal_id: activeGoal.id,
      new_learner_profile: JSON.stringify(activeGoal.learner_profile ?? {}),
    })
      .then(async (result) => {
        const r = result as typeof result & {
          adaptation?: { status?: string };
          learning_path?: unknown;
        };
        if (r.adaptation?.status === 'applied' && r.learning_path) {
          const updatedGoal = await patchGoalApi(userId, activeGoal.id, {
            learning_path: r.learning_path,
          });
          updateGoal(activeGoal.id, updatedGoal);
          void refetchRuntime();
        }
      })
      .catch(() => {})
      .finally(() => setIsAdapting(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runtimeState?.adaptation?.suggested, activeGoal?.id]);

  const handleLaunchSession = async (sessionIndex: number) => {
    if (!userId || !activeGoal) return;
    try {
      await sessionActivityApi({
        user_id: userId,
        goal_id: activeGoal.id,
        session_index: sessionIndex,
        event_type: 'start',
      });
    } catch {
      /* ignore */
    }
    navigate('/learning-session', { state: { goalId: activeGoal.id, sessionIndex } });
  };

  const learningPath = activeGoal?.learning_path ?? [];
  const fslsmInput = activeGoal?.learner_profile?.learning_preferences?.fslsm_dimensions?.fslsm_input;
  const threshold = config?.fslsm_activation_threshold ?? 0.3;
  const showModuleMap = typeof fslsmInput === 'number' && fslsmInput <= -threshold;
  const activeGoals = goals.filter((g) => !g.is_deleted);

  if (goalsLoading) {
    return (
      <div className="max-w-3xl space-y-4">
        <div className="bg-primary-50 border border-primary-200 rounded-lg px-4 py-3 text-sm text-primary-800 flex items-center gap-2">
          <span className="inline-block w-4 h-4 border-2 border-primary-400 border-t-transparent rounded-full animate-spin shrink-0" />
          Loading your goals…
        </div>
      </div>
    );
  }

  if (!activeGoal) {
    return (
      <div className="max-w-3xl space-y-4">
        <p className="text-slate-500">No active learning goal. Start by setting up a goal.</p>
        <Button onClick={() => navigate('/onboarding')}>Get Started</Button>
      </div>
    );
  }

  const goalTitle =
    (activeGoal.learner_profile?.goal_display_name as string | undefined) ?? activeGoal.learning_goal;

  if (isScheduling && learningPath.length === 0) {
    return (
      <PathGenerationLoading
        title={LEARNING_PATH_LOADING.title}
        steps={LEARNING_PATH_LOADING.steps}
        tips={LEARNING_PATH_LOADING.tips}
        goalTitle={goalTitle}
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6">
      {/* Header: Current goal + Goal dropdown */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <p className="text-base font-medium text-slate-800">
          Current Goal:{' '}
          <span className="text-slate-900">
            {(activeGoal.learner_profile?.goal_display_name as string | undefined) ?? activeGoal.learning_goal}
          </span>
        </p>
        {activeGoals.length > 1 && (
          <div className="flex items-center gap-3">
            <select
              value={selectedGoalId ?? ''}
              onChange={(e) => setSelectedGoalId(Number(e.target.value))}
              className="text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary-400 max-w-[200px]"
            >
              {activeGoals.map((g) => (
                <option key={g.id} value={g.id}>
                  {((g.learner_profile?.goal_display_name as string | undefined) ?? g.learning_goal).slice(0, 40)}
                </option>
              ))}
            </select>
            <Button variant="secondary" size="sm" className="shrink-0" onClick={refreshGoals}>
              Refresh
            </Button>
          </div>
        )}
      </div>

      {/* Schedule / adaptation banners */}
      {isScheduling && (
        <div className="bg-primary-50 border border-primary-200 rounded-lg px-4 py-3 text-sm text-primary-800 flex items-center gap-2">
          <span className="inline-block w-4 h-4 border-2 border-primary-400 border-t-transparent rounded-full animate-spin shrink-0" />
          Generating your personalised learning path… this may take a minute.
        </div>
      )}

      {isAdapting && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800 flex items-center gap-2">
          <span className="inline-block w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin shrink-0" />
          Adapting your learning path based on your progress…
        </div>
      )}

      {runtimeState?.adaptation?.suggested && !isAdapting && runtimeState.adaptation.message && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
          {runtimeState.adaptation.message}
        </div>
      )}

      {scheduleError && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 flex items-center justify-between gap-4">
          {scheduleError}
          <button
            className="text-red-600 underline text-xs shrink-0"
            onClick={() => {
              hasScheduledRef.current = false;
              setScheduleError(null);
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Two columns: Session list | Overall Progress-ish card */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Session list */}
        <div className="flex-1 space-y-3">
          {learningPath.length === 0 && !isScheduling ? (
            hasScheduledRef.current ? (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center text-slate-600 text-sm space-y-3">
                <p className="font-medium text-slate-800">
                  We couldn’t finish building your learning path.
                </p>
                <p className="text-xs text-slate-500 max-w-md mx-auto">
                  This can happen if the server took too long or the connection was interrupted. You can refresh your goals or come back and try again in a moment.
                </p>
                <div className="flex items-center justify-center gap-3 pt-2">
                  <Button size="sm" onClick={refreshGoals}>
                    Refresh goals
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => navigate('/goals')}>
                    Back to goals
                  </Button>
                </div>
              </div>
            ) : (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center text-slate-500 text-sm">
                No sessions yet. Your learning path will appear here once generated.
              </div>
            )
          ) : showModuleMap ? (
            <div className="space-y-1">
              {learningPath.map((session, idx) => {
                const runtime = runtimeState?.sessions.find((s) => s.session_index === idx);
                return (
                  <div key={(session.id as string | undefined) ?? idx} className="flex items-start gap-4">
                    <div className="flex flex-col items-center">
                      <div
                        className={cn(
                          'w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold border-2 shrink-0',
                          runtime?.if_learned
                            ? 'border-green-400 bg-green-100 text-green-700'
                            : runtime?.is_locked
                            ? 'border-slate-200 bg-slate-50 text-slate-400'
                            : 'border-primary-400 bg-primary-50 text-primary-700',
                        )}
                      >
                        {idx + 1}
                      </div>
                      {idx < learningPath.length - 1 && <div className="w-0.5 h-6 bg-slate-200 mt-1" />}
                    </div>
                    <div className="flex-1 pb-4">
                      <SessionCard
                        index={idx}
                        pathSession={session}
                        runtimeSession={runtime}
                        onLaunch={() => handleLaunchSession(idx)}
                        disabled={isScheduling || isAdapting}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="space-y-3">
              {learningPath.map((session, idx) => {
                const runtime = runtimeState?.sessions.find((s) => s.session_index === idx);
                return (
                  <SessionCard
                    key={(session.id as string | undefined) ?? idx}
                    index={idx}
                    pathSession={session}
                    runtimeSession={runtime}
                    onLaunch={() => handleLaunchSession(idx)}
                    disabled={isScheduling || isAdapting}
                  />
                );
              })}
            </div>
          )}
        </div>

        {/* Right-side small card reusing existing beta look */}
        <div className="lg:w-72 shrink-0">
          <div className="bg-white rounded-xl border border-slate-200 p-5 sticky top-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-800 mb-1">Path Status</h3>
            <p className="text-xs text-slate-500">
              Sessions: <span className="font-semibold text-slate-700">{learningPath.length}</span>
            </p>
            {runtimeState && (
              <p className="text-xs text-slate-500">
                Completed:{' '}
                <span className="font-semibold text-slate-700">
                  {runtimeState.sessions.filter((s) => s.if_learned).length}
                </span>
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
