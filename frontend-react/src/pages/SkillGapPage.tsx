import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Button, Toggle } from '@/components/ui';
import { cn } from '@/lib/cn';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useAppConfig } from '@/api/endpoints/config';
import {
  useIdentifySkillGap,
  useAuditSkillGapBias,
  useCreateLearnerProfileWithInfo,
  useValidateProfileFairness,
} from '@/api/endpoints/skillGap';
import { createGoalApi } from '@/api/endpoints/goals';
import { syncProfileApi } from '@/api/endpoints/profile';

/* ─────────────────────────────── types ─────────────────────────────────── */

interface LocationState {
  goal: string;
  personaKey: string | null;
  learnerInformation: string;
  isGoalManagementFlow: boolean;
}

interface SkillGapItem {
  skill_name: string;
  current_level: string;
  required_level: string;
  is_gap: boolean;
  [key: string]: unknown;
}

interface LocalSkill {
  original: SkillGapItem;
  current_level: string;
  required_level: string;
  addToPlan: boolean;
}

/* ─────────────────────────────── sub-components ───────────────────────── */

function LevelTrack({
  label,
  level,
  levels,
  variant,
  onLevelChange,
  disabled,
}: {
  label: string;
  level: string;
  levels: string[];
  variant: 'target' | 'current';
  onLevelChange?: (next: string) => void;
  disabled?: boolean;
}) {
  const idx = Math.max(0, levels.indexOf(level));
  const pct = levels.length > 1 ? (idx / (levels.length - 1)) * 100 : 0;
  const interactive = !!onLevelChange && !disabled;

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-slate-500 w-14 shrink-0">{label}</span>
      <div className="relative flex-1 h-7 flex items-center">
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-1.5 rounded-full bg-slate-200" />
        <div
          className={cn(
            'absolute top-1/2 -translate-y-1/2 left-0 h-1.5 rounded-full transition-all duration-150',
            variant === 'target' ? 'bg-primary-500' : 'bg-primary-300',
          )}
          style={{ width: `${pct}%` }}
        />
        {levels.map((lv, i) => {
          const x = levels.length > 1 ? (i / (levels.length - 1)) * 100 : 0;
          const isActive = i <= idx;
          return (
            <button
              key={lv}
              type="button"
              disabled={!interactive}
              onClick={() => onLevelChange?.(lv)}
              title={interactive ? `Set to ${lv}` : lv}
              className={cn(
                'absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 rounded-full transition-all border-2',
                isActive
                  ? variant === 'target'
                    ? 'bg-primary-600 border-primary-600'
                    : 'bg-primary-400 border-primary-400'
                  : 'bg-white border-slate-300',
                interactive
                  ? 'hover:scale-125 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400'
                  : 'cursor-default',
              )}
              style={{ left: `${x}%` }}
            />
          );
        })}
      </div>
    </div>
  );
}

function LevelLabels({ levels }: { levels: string[] }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-14 shrink-0" />
      <div className="relative flex-1 flex justify-between">
        {levels.map((l) => (
          <span key={l} className="text-[10px] text-slate-400">{l}</span>
        ))}
      </div>
    </div>
  );
}

function SkillCard({
  skill,
  levels,
  onToggle,
  onTargetChange,
  onCurrentChange,
  disabled,
}: {
  skill: LocalSkill;
  levels: string[];
  onToggle: () => void;
  onTargetChange: (level: string) => void;
  onCurrentChange: (level: string) => void;
  disabled: boolean;
}) {
  const curIdx = Math.max(0, levels.indexOf(skill.current_level));
  const reqIdx = Math.max(0, levels.indexOf(skill.required_level));
  const gap = Math.max(0, reqIdx - curIdx);

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <h3 className="font-semibold text-slate-800">{skill.original.skill_name}</h3>
        <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-slate-100 text-slate-700">
          Gap: {gap} level{gap !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="px-5 space-y-1.5">
        <LevelTrack
          label="Required"
          level={skill.required_level}
          levels={levels}
          variant="target"
          onLevelChange={onTargetChange}
          disabled={disabled}
        />
        <LevelTrack
          label="Current"
          level={skill.current_level}
          levels={levels}
          variant="current"
          onLevelChange={onCurrentChange}
          disabled={disabled}
        />
        <LevelLabels levels={levels} />
      </div>
      <div className="flex items-center justify-end gap-4 px-5 py-3 mt-2 border-t border-slate-100">
        <Toggle
          label={skill.addToPlan ? 'Add to Plan' : 'Ignore'}
          checked={skill.addToPlan}
          onChange={onToggle}
          disabled={disabled}
        />
      </div>
    </div>
  );
}

/* ─────────────────────────────── page ──────────────────────────────────── */

export function SkillGapPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { userId } = useAuthContext();
  const { setSelectedGoalId, refreshGoals } = useGoalsContext();
  const { data: config } = useAppConfig();

  const state = location.state as LocationState | null;

  useEffect(() => {
    if (!state?.goal || !state?.learnerInformation) {
      navigate('/onboarding', { replace: true });
    }
  }, [state, navigate]);

  const levels = config?.skill_levels ?? ['Unlearned', 'Beginner', 'Intermediate', 'Advanced'];

  const identifyMutation = useIdentifySkillGap();
  const auditMutation = useAuditSkillGapBias();
  const createProfileMutation = useCreateLearnerProfileWithInfo();
  const validateFairnessMutation = useValidateProfileFairness();

  const [identifyResponse, setIdentifyResponse] = useState<Record<string, unknown> | null>(null);
  const [biasAudit, setBiasAudit] = useState<Record<string, unknown> | null>(null);
  const [localSkills, setLocalSkills] = useState<LocalSkill[]>([]);
  const [isScheduling, setIsScheduling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasFiredRef = useRef(false);

  useEffect(() => {
    if (hasFiredRef.current || !state?.goal || !state?.learnerInformation) return;
    hasFiredRef.current = true;
    identifyMutation.mutate(
      { learning_goal: state.goal, learner_information: state.learnerInformation },
      {
        onSuccess: (data) => {
          const resp = data as Record<string, unknown>;
          setIdentifyResponse(resp);
          const rawGaps = resp.skill_gaps;
          const gapArray: SkillGapItem[] = Array.isArray(rawGaps)
            ? (rawGaps as SkillGapItem[])
            : rawGaps && typeof rawGaps === 'object'
            ? Object.values(rawGaps as Record<string, SkillGapItem>)
            : [];
          setLocalSkills(
            gapArray.map((sg) => ({
              original: sg,
              current_level: sg.current_level ?? levels[0],
              required_level: sg.required_level ?? (levels[1] ?? levels[0]),
              addToPlan: sg.is_gap !== false,
            })),
          );
          auditMutation.mutate(
            { skill_gaps: JSON.stringify(gapArray), learner_information: state.learnerInformation },
            {
              onSuccess: (biasData) => setBiasAudit(biasData as Record<string, unknown>),
              onError: () => {},
            },
          );
        },
        onError: () => setError('Failed to identify skill gaps. Please try again.'),
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleToggle = useCallback((idx: number) => {
    setLocalSkills((prev) => prev.map((s, i) => (i === idx ? { ...s, addToPlan: !s.addToPlan } : s)));
  }, []);

  const handleTargetChange = useCallback((idx: number, level: string) => {
    setLocalSkills((prev) => prev.map((s, i) => (i === idx ? { ...s, required_level: level } : s)));
  }, []);

  const handleCurrentChange = useCallback((idx: number, level: string) => {
    setLocalSkills((prev) => prev.map((s, i) => (i === idx ? { ...s, current_level: level } : s)));
  }, []);

  const plannedSkills = localSkills.filter((s) => s.addToPlan);
  const hasGaps = plannedSkills.some((s) => levels.indexOf(s.required_level) > levels.indexOf(s.current_level));

  const goalAssessment = (identifyResponse?.goal_assessment as Record<string, unknown> | undefined) ?? null;
  const autoRefined = goalAssessment?.auto_refined === true;
  const refinedGoal = (goalAssessment?.refined_goal as string | undefined) ?? state?.goal ?? '';
  const isVague = goalAssessment?.vague === true;
  const allMastered = goalAssessment?.all_mastered === true;
  const retrievedSources = (identifyResponse?.retrieved_sources as unknown[] | undefined) ?? [];
  const biasWarnings = (biasAudit?.warnings as string[] | undefined) ?? [];
  const ethicalDisclaimer = (biasAudit?.ethical_disclaimer as string | undefined) ?? '';

  const handleSchedule = useCallback(async () => {
    if (!userId || !state) return;
    setIsScheduling(true);
    setError(null);
    try {
      const filteredGaps = plannedSkills.map((s) => ({
        ...s.original,
        current_level: s.current_level,
        required_level: s.required_level,
      }));

      const profileResult = await createProfileMutation.mutateAsync({
        learning_goal: refinedGoal,
        learner_information: state.learnerInformation,
        skill_gaps: JSON.stringify(filteredGaps),
      });
      const learnerProfile = profileResult.learner_profile;

      let profileFairness: Record<string, unknown> | null = null;
      if (!state.isGoalManagementFlow) {
        try {
          profileFairness = (await validateFairnessMutation.mutateAsync({
            learner_profile: JSON.stringify(learnerProfile),
            learner_information: state.learnerInformation,
            persona_name: state.personaKey ?? '',
          })) as Record<string, unknown>;
        } catch {
          profileFairness = null;
        }
      }

      const newGoal = await createGoalApi(userId, {
        learning_goal: refinedGoal,
        skill_gaps: filteredGaps as unknown,
        goal_assessment: goalAssessment,
        goal_context: identifyResponse?.goal_context,
        retrieved_sources: retrievedSources,
        bias_audit: biasAudit,
        profile_fairness: profileFairness,
        learner_profile: learnerProfile,
      });

      try { await syncProfileApi(userId, newGoal.id); } catch { /* ignore */ }

      refreshGoals();
      setSelectedGoalId(newGoal.id);
      navigate('/learning-path');
    } catch {
      setError('Failed to create your learning path. Please try again.');
    } finally {
      setIsScheduling(false);
    }
  }, [userId, state, plannedSkills, refinedGoal, goalAssessment, identifyResponse, retrievedSources, biasAudit, createProfileMutation, validateFairnessMutation, refreshGoals, setSelectedGoalId, navigate]);

  if (!state?.goal) return null;

  if (identifyMutation.isPending) {
    return (
      <div className="max-w-3xl space-y-6">
        <div className="bg-primary-50 border border-primary-200 rounded-lg px-4 py-3 text-sm text-primary-800 flex items-center gap-2">
          <span className="inline-block w-4 h-4 border-2 border-primary-400 border-t-transparent rounded-full animate-spin shrink-0" />
          Analysing skill gaps for <strong className="ml-1">{state.goal}</strong>…
        </div>
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl border border-slate-200 p-6 space-y-4 animate-pulse">
            <div className="flex justify-between">
              <div className="h-5 w-48 bg-slate-200 rounded" />
              <div className="h-5 w-24 bg-slate-100 rounded-full" />
            </div>
            <div className="h-6 bg-slate-100 rounded" />
            <div className="h-6 bg-slate-100 rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (error && !identifyResponse) {
    return (
      <div className="max-w-3xl space-y-4">
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">{error}</div>
        <Button variant="secondary" onClick={() => navigate('/onboarding')}>Back to Onboarding</Button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <button type="button" onClick={() => navigate('/onboarding')} className="text-sm text-slate-500 hover:text-slate-700 flex items-center gap-1 mb-4">
          ← Back to Onboarding
        </button>
        <h2 className="text-xl font-semibold text-slate-800">Skill Gap Analysis</h2>
        <p className="mt-1 text-sm text-slate-500">
          Learning goal: <strong className="text-slate-700">{refinedGoal}</strong>
        </p>
      </div>

      {autoRefined && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-800">
          Your goal was automatically refined: <strong>{refinedGoal}</strong>
        </div>
      )}
      {isVague && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
          Your goal may be too broad. Consider being more specific for better personalisation.
        </div>
      )}
      {allMastered && (
        <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-800">
          Great news — you appear to already have strong knowledge of this topic!
        </div>
      )}
      {biasWarnings.length > 0 && (
        <div className="bg-orange-50 border border-orange-200 rounded-lg px-4 py-3 text-sm text-orange-800">
          <p className="font-medium mb-1">Bias audit notes:</p>
          <ul className="list-disc list-inside space-y-0.5">{biasWarnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </div>
      )}
      {ethicalDisclaimer && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-xs text-slate-600">{ethicalDisclaimer}</div>
      )}

      <p className="text-sm text-slate-600">
        We identified <strong>{localSkills.length}</strong> skill{localSkills.length !== 1 ? 's' : ''} relevant to your goal.{' '}
        Toggle skills below to include them in your learning plan.
      </p>

      <div className="space-y-4">
        {localSkills.map((skill, idx) => (
          <SkillCard
            key={skill.original.skill_name + idx}
            skill={skill}
            levels={levels}
            onToggle={() => handleToggle(idx)}
            onTargetChange={(level) => handleTargetChange(idx, level)}
            onCurrentChange={(level) => handleCurrentChange(idx, level)}
            disabled={isScheduling}
          />
        ))}
      </div>

      {retrievedSources.length > 0 && (
        <details className="text-sm border border-slate-200 rounded-lg">
          <summary className="px-4 py-3 cursor-pointer text-slate-600 font-medium select-none">
            Retrieved sources ({retrievedSources.length})
          </summary>
          <ul className="px-4 pb-4 pt-1 space-y-1 text-xs text-slate-500 list-disc list-inside">
            {retrievedSources.slice(0, 5).map((src, i) => (
              <li key={i}>{typeof src === 'string' ? src : JSON.stringify(src)}</li>
            ))}
          </ul>
        </details>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <div className="flex items-center justify-between gap-4 pt-4 pb-8">
        <Button variant="secondary" onClick={() => navigate('/onboarding')} disabled={isScheduling}>
          Edit Goal
        </Button>
        <Button
          size="lg"
          onClick={handleSchedule}
          loading={isScheduling}
          disabled={plannedSkills.length === 0 || !hasGaps || isScheduling}
          className="px-8"
        >
          {isScheduling ? 'Creating your profile…' : 'Schedule Learning Path'}
        </Button>
      </div>
    </div>
  );
}
