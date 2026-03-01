import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui';
import { SessionCard } from '@/components/learning/SessionCard';
import { cn } from '@/lib/cn';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/hooks/useActiveGoal';
import { useAppConfig } from '@/api/endpoints/config';
import { useGoalRuntimeState, patchGoalApi } from '@/api/endpoints/goals';
import { scheduleLearningPathAgenticApi, adaptLearningPathApi } from '@/api/endpoints/learningPath';
import { sessionActivityApi } from '@/api/endpoints/content';

export function LearningPathPage() {
  const navigate = useNavigate();
  const { userId } = useAuthContext();
  const { goals, selectedGoalId, setSelectedGoalId, refreshGoals, updateGoal } = useGoalsContext();
  const { data: config } = useAppConfig();
  const activeGoal = useActiveGoal();

  const [isScheduling, setIsScheduling] = useState(false);
  const [isAdapting, setIsAdapting] = useState(false);
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
        if (result.adaptation?.status === 'applied' && result.learning_path) {
          const updatedGoal = await patchGoalApi(userId, activeGoal.id, {
            learning_path: result.learning_path,
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
    } catch { /* ignore */ }
    navigate('/learning-session', { state: { goalId: activeGoal.id, sessionIndex } });
  };

  const learningPath = activeGoal?.learning_path ?? [];
  const evaluation = activeGoal?.plan_agent_metadata?.evaluation;
  const fslsmInput = activeGoal?.learner_profile?.learning_preferences?.fslsm_dimensions?.fslsm_input;
  const threshold = config?.fslsm_activation_threshold ?? 0.3;
  const showModuleMap = typeof fslsmInput === 'number' && fslsmInput <= -threshold;
  const activeGoals = goals.filter((g) => !g.is_deleted);

  if (!activeGoal) {
    return (
      <div className="max-w-3xl space-y-4">
        <p className="text-slate-500">No active learning goal. Start by setting up a goal.</p>
        <Button onClick={() => navigate('/onboarding')}>Get Started</Button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-800">Learning Path</h2>
          <p className="mt-1 text-sm text-slate-500 line-clamp-2">
            {(activeGoal.learner_profile?.goal_display_name as string | undefined) ?? activeGoal.learning_goal}
          </p>
        </div>
        {activeGoals.length > 1 && (
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
        )}
      </div>

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
            onClick={() => { hasScheduledRef.current = false; setScheduleError(null); }}
          >
            Retry
          </button>
        </div>
      )}

      {evaluation && (
        <div className={cn(
          'rounded-lg border px-4 py-3 text-sm',
          evaluation.pass
            ? 'bg-green-50 border-green-200 text-green-800'
            : 'bg-amber-50 border-amber-200 text-amber-800',
        )}>
          <p className="font-medium mb-1">
            Plan Quality: {evaluation.pass ? 'Approved' : 'Needs Review'}
          </p>
          {evaluation.feedback_summary && (
            <p className="text-xs">{evaluation.feedback_summary}</p>
          )}
        </div>
      )}

      {learningPath.length === 0 && !isScheduling ? (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center text-slate-500 text-sm">
          No sessions yet. Your learning path will appear here once generated.
        </div>
      ) : showModuleMap ? (
        <div className="space-y-1">
          <p className="text-xs text-slate-400 font-medium uppercase tracking-wider mb-3">Module View</p>
          {learningPath.map((session, idx) => {
            const runtime = runtimeState?.sessions.find((s) => s.session_index === idx);
            return (
              <div key={(session.id as string | undefined) ?? idx} className="flex items-start gap-4">
                <div className="flex flex-col items-center">
                  <div className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold border-2 shrink-0',
                    runtime?.if_learned
                      ? 'border-green-400 bg-green-100 text-green-700'
                      : runtime?.is_locked
                      ? 'border-slate-200 bg-slate-50 text-slate-400'
                      : 'border-primary-400 bg-primary-50 text-primary-700',
                  )}>
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

      <div className="flex justify-end">
        <Button variant="secondary" size="sm" onClick={refreshGoals} disabled={isScheduling}>
          Refresh
        </Button>
      </div>
    </div>
  );
}
