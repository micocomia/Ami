import { useCallback, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { Button, Toggle } from '@/components/ui';
import { cn } from '@/lib/cn';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useSidebarCollapse } from '@/context/SidebarCollapseContext';
import { useAppConfig } from '@/api/endpoints/config';
import {
  useCreateLearnerProfileWithInfo,
  useValidateProfileFairness,
  identifySkillGapApi,
  auditSkillGapBiasApi,
} from '@/api/endpoints/skillGap';
import { createGoalApi } from '@/api/endpoints/goals';
import { syncProfileApi } from '@/api/endpoints/profile';
import { pushAppState } from '@/components/DebugPanel';
import { PathGenerationLoading } from '@/components/learning/PathGenerationLoading';

/* ------------------------------------------------------------------ */
/*  Loading stage copy (reused for skill gap vs learning path)        */
/* ------------------------------------------------------------------ */

const SKILL_GAP_LOADING = {
  title: 'Building your skill gap profile',
  subtitle: "We're analyzing your goal and identifying the most important skills to improve first.",
  steps: [
    'Understanding your learning goal...',
    'Breaking down required skills...',
    'Checking your current gaps...',
    'Identifying priority improvement areas...',
    'Preparing your skill gap analysis...',
  ],
  tips: [
    'Tip: Clear goals lead to more accurate learning recommendations.',
    'Tip: Finding weak spots early helps you improve faster.',
    'Tip: Skill gaps are easier to close when broken into smaller targets.',
    'Tip: Strong learning plans start with honest assessment.',
  ],
};

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
};

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

interface LocationState {
  goal: string;
  personaKey: string | null;
  learnerInformation: string;
  isGoalManagementFlow: boolean;
}

/** Mirrors backend modules.skill_gap.schemas.SkillGap (+ optional extras) */
interface SkillGapItem {
  name?: string;
  skill_name?: string;
  current_level: string;
  required_level: string;
  is_gap: boolean;
  /** Backend: concise rationale for current level (≤20 words) */
  reason?: string;
  level_confidence?: string;
  [key: string]: unknown;
}

interface LocalSkill {
  original: SkillGapItem;
  current_level: string;
  required_level: string;
  addToPlan: boolean;
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function formatLevelLabel(level: string) {
  if (!level) return '';
  return level.charAt(0).toUpperCase() + level.slice(1);
}

/** Match backend/config level string to levels[] entry so indexOf/gapLv work after adjust */
function normalizeLevel(level: string | undefined, levels: string[]): string {
  if (!level || !levels.length) return level ?? '';
  const lower = String(level).toLowerCase();
  const found = levels.find((x) => String(x).toLowerCase() === lower);
  return found ?? level;
}

/**
 * Backend gap objects may expose level under different keys or as enum-like { value: "beginner" }.
 * Avoid defaulting to unlearned when the API actually sent another level in an alternate field.
 */
function coerceLevelFromGap(sg: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = sg[k];
    if (v == null) continue;
    if (typeof v === 'string') {
      const s = v.trim();
      if (s) return s;
      continue;
    }
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      const o = v as Record<string, unknown>;
      if (typeof o.value === 'string' && o.value.trim()) return o.value.trim();
    }
  }
  return '';
}

/**
 * Backend + config may disagree on level strings; indexOf alone gives -1 and breaks bars/gap.
 * Fixed order matches backend LevelCurrent/LevelRequired.
 */
const LEVEL_ORDER: Record<string, number> = {
  unlearned: 0,
  beginner: 1,
  intermediate: 2,
  advanced: 3,
  expert: 4,
};

function levelIndex(level: string | undefined, levels: string[]): number {
  if (!level) return 0;
  const normalized = normalizeLevel(level, levels);
  const i = levels.indexOf(normalized);
  if (i >= 0) return i;
  const key = String(level).toLowerCase();
  if (key in LEVEL_ORDER) return LEVEL_ORDER[key];
  return 0;
}

const SKILLGAP_STORAGE_KEY = 'ami_skillgap_adjusted_v1';

function skillGapStorageKey(goal: string, learnerInformation: string): string {
  const slice = `${goal}\n${learnerInformation}`.slice(0, 500);
  let h = 0;
  for (let i = 0; i < slice.length; i++) h = (h * 31 + slice.charCodeAt(i)) | 0;
  return `${SKILLGAP_STORAGE_KEY}_${h}`;
}

/**
 * Backend create-learner-profile-with-info parses skill_gaps with ast.literal_eval only.
 * JSON.stringify produces JSON (double quotes) which literal_eval cannot parse.
 * Emit Python literal syntax so backend receives a list of dicts without backend changes.
 */
function skillGapsToPythonLiteral(value: unknown): string {
  if (value === null || value === undefined) return 'None';
  if (typeof value === 'boolean') return value ? 'True' : 'False';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 'None';
    return String(value);
  }
  if (typeof value === 'string') {
    return "'" + value.replace(/\\/g, '\\\\').replace(/'/g, "\\'") + "'";
  }
  if (Array.isArray(value)) {
    return '[' + value.map((v) => skillGapsToPythonLiteral(v)).join(', ') + ']';
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).filter(
      ([, v]) => v !== undefined,
    );
    return (
      '{' +
      entries
        .map(([k, v]) => skillGapsToPythonLiteral(k) + ': ' + skillGapsToPythonLiteral(v))
        .join(', ') +
      '}'
    );
  }
  return 'None';
}

/** Backend LevelRequired has no unlearned — target track must not offer it */
function levelsWithoutUnlearned(levels: string[]): string[] {
  const filtered = levels.filter((l) => String(l).toLowerCase() !== 'unlearned');
  return filtered.length > 0 ? filtered : levels;
}

type SavedSkill = {
  name?: string;
  current_level: string;
  required_level: string;
  addToPlan?: boolean;
};

/** Apply sessionStorage skills by name first; index only when name matches or single fallback */
function applySavedSkillsToMapped(
  mapped: LocalSkill[],
  savedSkills: SavedSkill[],
  levels: string[],
): void {
  const byName = new Map<string, SavedSkill>();
  for (const s of savedSkills) {
    const k = (s.name ?? '').toString().toLowerCase().trim();
    if (k) byName.set(k, s);
  }
  for (let i = 0; i < mapped.length; i++) {
    const m = mapped[i];
    const nameKey = (m.original.skill_name || m.original.name || '').toString().toLowerCase().trim();
    let toApply = nameKey ? byName.get(nameKey) : undefined;
    /* Index fallback only when names align or both unnamed */
    if (!toApply && savedSkills[i]) {
      const sn = (savedSkills[i].name ?? '').toString().toLowerCase().trim();
      if (!sn || sn === nameKey) toApply = savedSkills[i];
    }
    if (!toApply) continue;
    if (toApply.current_level)
      m.current_level = normalizeLevel(toApply.current_level, levels);
    if (toApply.required_level) {
      let req = normalizeLevel(toApply.required_level, levels);
      if (String(req).toLowerCase() === 'unlearned')
        req = levelsWithoutUnlearned(levels)[0] ?? req;
      m.required_level = req;
    }
    if (typeof toApply.addToPlan === 'boolean') m.addToPlan = toApply.addToPlan;
    const cur = levelIndex(m.current_level, levels);
    const tgt = levelIndex(m.required_level, levels);
    m.original = {
      ...m.original,
      current_level: m.current_level,
      required_level: m.required_level,
      is_gap: tgt > cur,
    };
  }
}

/** Horizontal level track: click stage to select (no dropdown) */
function LevelTrackRow({
  rowLabel,
  value,
  levels,
  onChange,
  disabled,
  variant = 'current',
}: {
  rowLabel: string;
  value: string;
  levels: string[];
  onChange: (next: string) => void;
  disabled?: boolean;
  /** target = destination level (cool/teal); current = where learner is (warm/amber) */
  variant?: 'target' | 'current';
}) {
  const selectedIdx = levelIndex(value, levels);
  const n = levels.length;
  const isTarget = variant === 'target';
  const totalSlots = isTarget ? n + 1 : n;
  const maxSlotIdx = Math.max(totalSlots - 1, 1);
  const fillPct =
    isTarget
      ? ((selectedIdx + 1) / maxSlotIdx) * 100
      : (selectedIdx / Math.max(n - 1, 1)) * 100;

  /*
   * Minimal distinction: same neutral shell, different accent only.
   * Target = cool slate (destination); Current = primary (where you are).
   */
  /* Track #D7E3E8; current row fill #1FA89A (target row stays slate for distinction) */
  const styles = isTarget
    ? {
        label: 'text-[#7E92A3]',
        accentBar: 'bg-[#5F7486]',
        fill: 'bg-[#5F7486]',
        selectedDot: 'bg-[#16324A]',
        pastDotLg: 'bg-[#5F7486]',
        pastDotSm: 'bg-[#7E92A3]',
        labelSelected: 'text-[#16324A]',
        focusRing: 'focus-visible:ring-[#8FC7D1]',
      }
    : {
        label: 'text-[#7E92A3]',
        accentBar: 'bg-[#1FA89A]',
        fill: 'bg-[#1FA89A]',
        selectedDot: 'bg-[#148A7D]',
        pastDotLg: 'bg-[#1FA89A]',
        pastDotSm: 'bg-[#4AB9AD]',
        labelSelected: 'text-[#16324A]',
        focusRing: 'focus-visible:ring-[#8FC7D1]',
      };

  return (
    <div className="min-w-0">
      <div className="mb-2 flex items-center gap-2">
        <span className={cn('h-1 w-1 rounded-full shrink-0', styles.accentBar)} aria-hidden />
        <p className={cn('text-[10px] font-semibold uppercase tracking-wider', styles.label)}>
          {rowLabel}
        </p>
      </div>
      <div className="relative">
        <div className="h-2 w-full rounded-full bg-[#D7E3E8]" />
        <div
          className={cn('absolute left-0 top-0 h-2 rounded-full transition-[width] duration-200', styles.fill)}
          style={{ width: `${fillPct}%`, minWidth: selectedIdx === 0 && !isTarget ? 12 : undefined }}
        />
        <div className="absolute inset-0 flex">
          {levels.map((level, idx) => {
            const isSelected = idx === selectedIdx;
            const isPast = idx <= selectedIdx;
            const leftPct = isTarget
              ? ((idx + 1) / maxSlotIdx) * 100
              : n > 1 ? (idx / (n - 1)) * 100 : 0;
            return (
              <button
                key={level}
                type="button"
                disabled={disabled}
                aria-label={`Set ${rowLabel} to ${formatLevelLabel(level)}`}
                aria-pressed={isSelected}
                onClick={() => onChange(level)}
                className={cn(
                  'absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full p-1.5 outline-none transition-transform hover:scale-110 focus-visible:ring-2 disabled:pointer-events-none disabled:opacity-50',
                  styles.focusRing,
                )}
                style={{ left: `${leftPct}%` }}
              >
                {isSelected ? (
                  <div
                    className={cn('h-2.5 w-2.5 rounded-sm shadow-sm ring-2 ring-white', styles.selectedDot)}
                  />
                ) : idx === 0 ? (
                  <div
                    className={cn(
                      'h-2 w-2 rounded-full ring-2 ring-white',
                      isPast ? styles.pastDotLg : 'bg-slate-300',
                    )}
                  />
                ) : (
                  <div
                    className={cn(
                      'h-1.5 w-1.5 rounded-full ring-2 ring-white',
                      isPast ? styles.pastDotSm : 'bg-slate-300',
                    )}
                  />
                )}
              </button>
            );
          })}
        </div>
      </div>
      <div
        className="mt-2 grid gap-0.5 text-center"
        style={{
          gridTemplateColumns: `repeat(${isTarget ? n + 1 : n}, minmax(0, 1fr))`,
        }}
      >
        {isTarget && (
          <div className="rounded-md px-0.5 py-1 text-[10px] leading-tight text-[#C0CDD6]">
            {formatLevelLabel('unlearned')}
          </div>
        )}
        {levels.map((level, idx) => {
          const isSelected = idx === selectedIdx;
          return (
            <button
              key={level}
              type="button"
              disabled={disabled}
              onClick={() => onChange(level)}
              className={cn(
                'rounded-md px-0.5 py-1 text-[10px] leading-tight transition-colors',
                'hover:bg-[#F7FBFC] focus-visible:outline-none focus-visible:ring-2',
                styles.focusRing,
                disabled && 'cursor-not-allowed opacity-50',
                isSelected
                  ? cn('font-semibold', styles.labelSelected)
                  : 'text-[#5F7486] hover:text-[#16324A]',
              )}
            >
              {formatLevelLabel(level)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Normalize backend string fields; returns null if empty */
function stringFromBackend(v: unknown): string | null {
  if (v == null) return null;
  const s = String(v).trim();
  return s.length > 0 ? s : null;
}

/* ------------------------------------------------------------------ */
/*  Sub-component: SkillCard                                         */
/* ------------------------------------------------------------------ */

function SkillCard({
  index,
  skill,
  levels,
  onToggle,
  onTargetChange,
  onCurrentChange,
  disabled,
}: {
  index: number;
  skill: LocalSkill;
  levels: string[];
  onToggle: () => void;
  onTargetChange: (level: string) => void;
  onCurrentChange: (level: string) => void;
  disabled: boolean;
}) {
  const title =
    stringFromBackend(skill.original.name) ??
    stringFromBackend(skill.original.skill_name) ??
    'Skill';

  // All narrative copy from backend only
  const reason = stringFromBackend(skill.original.reason);
  const levelConfidence = stringFromBackend(skill.original.level_confidence);
  const suggestedPath = stringFromBackend(
    (skill.original as Record<string, unknown>).suggested_growth_path,
  );
  const currentDescription = stringFromBackend(
    (skill.original as Record<string, unknown>).current_level_description,
  );

  const hasExpandableContent =
    Boolean(reason || suggestedPath || currentDescription || levelConfidence);

  const [expanded, setExpanded] = useState(false);

  return (
    <div className="overflow-hidden rounded-2xl border border-[#DCE7EA] bg-white shadow-[0_1px_3px_rgba(22,50,74,0.06)]">
      {/* Header: numbered title + Mark as Gap */}
      <div className="flex items-center justify-between gap-3 px-4 pt-4 pb-3">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[#DCE7EA] bg-white text-sm font-semibold text-[#7E92A3]"
            aria-hidden
          >
            {index + 1}
          </span>
          <h3 className="truncate text-base font-semibold text-[#16324A]">{title}</h3>
        </div>
        <Toggle
          label="Mark as Gap"
          checked={skill.addToPlan}
          onChange={() => onToggle()}
          disabled={disabled}
          className="shrink-0 [&_span]:text-xs [&_span]:text-[#5F7486]"
        />
      </div>

      {/* REQUIRED + CURRENT tracks — required excludes unlearned (backend LevelRequired) */}
      <div className="space-y-6 border-t border-slate-100 px-4 pb-4 pt-4">
        <LevelTrackRow
          variant="target"
          rowLabel="Required level"
          value={skill.required_level}
          levels={levelsWithoutUnlearned(levels)}
          onChange={onTargetChange}
          disabled={disabled}
        />
        <LevelTrackRow
          variant="current"
          rowLabel="Current level"
          value={skill.current_level}
          levels={levels}
          onChange={onCurrentChange}
          disabled={disabled}
        />
      </div>

      {/* Expandable: only backend-provided strings; no fabricated copy */}
      {hasExpandableContent && (
        <div className="border-t border-slate-100 bg-slate-50/50">
          <button
            type="button"
            disabled={disabled}
            onClick={() => setExpanded((e) => !e)}
            className="flex w-full items-center justify-between px-4 py-2.5 text-left text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          >
            <span>{expanded ? 'Collapse' : 'Expand'} details</span>
            <span className={cn('text-slate-600 transition-transform', expanded && 'rotate-180')}>▾</span>
          </button>
          {expanded && (
            <div className="space-y-4 px-4 pb-4">
              {reason && (
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[#7E92A3]">
                    Assessment
                  </p>
                  <p className="text-sm leading-relaxed text-[#16324A]">{reason}</p>
                </div>
              )}
              {currentDescription && (
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[#7E92A3]">
                    Current level
                  </p>
                  <p className="text-sm leading-relaxed text-[#16324A]">{currentDescription}</p>
                </div>
              )}
              {suggestedPath && (
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[#7E92A3]">
                    Suggested growth path
                  </p>
                  <p className="text-sm leading-relaxed text-[#16324A]">{suggestedPath}</p>
                </div>
              )}
              {levelConfidence && (
                <p className="text-[11px] text-[#5F7486]">
                  <span className="font-medium text-[#16324A]">Confidence:</span> {levelConfidence}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page component                                                    */
/* ------------------------------------------------------------------ */

export function SkillGapPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { collapsed } = useSidebarCollapse();
  const { userId } = useAuthContext();
  const { setSelectedGoalId, refreshGoals } = useGoalsContext();
  const { data: config } = useAppConfig();

  const state = location.state as LocationState | null;

  useEffect(() => {
    if (!state?.goal || !state?.learnerInformation) {
      navigate('/onboarding', { replace: true });
    }
  }, [state, navigate]);

  const levels = config?.skill_levels ?? ['unlearned', 'beginner', 'intermediate', 'advanced', 'expert'];

  const createProfileMutation = useCreateLearnerProfileWithInfo();
  const validateFairnessMutation = useValidateProfileFairness();

  const [identifyResponse, setIdentifyResponse] = useState<Record<string, unknown> | null>(null);
  const [biasAudit, setBiasAudit] = useState<Record<string, unknown> | null>(null);
  const [localSkills, setLocalSkills] = useState<LocalSkill[]>([]);
  const [isScheduling, setIsScheduling] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** false = default overview (summary cards); true = detailed adjust UI (tracks + toggles) */
  const [adjustMode, setAdjustMode] = useState(false);
  const hasFiredRef = useRef(false);
  /** Snapshot when entering adjust mode — Cancel restores this */
  const adjustSnapshotRef = useRef<LocalSkill[] | null>(null);
  /** Always holds latest localSkills so saveAdjust reads edits made in adjust UI (avoids stale prev) */
  const localSkillsRef = useRef<LocalSkill[]>([]);
  useEffect(() => {
    localSkillsRef.current = localSkills;
  }, [localSkills]);
  /** Bump to force overview remount after save so list/aside always reflect adjusted levels */
  const [overviewEpoch, setOverviewEpoch] = useState(0);
  /** Overview list selection — hooks must run before any early return */
  const [selectedSkillIdx, setSelectedSkillIdx] = useState(0);
  useEffect(() => {
    if (localSkills.length > 0 && selectedSkillIdx >= localSkills.length) {
      setSelectedSkillIdx(0);
    }
  }, [localSkills.length, selectedSkillIdx]);

  void function enterAdjustMode() {
    adjustSnapshotRef.current = structuredClone(localSkills) as LocalSkill[];
    setAdjustMode(true);
  };

  const cancelAdjust = useCallback(() => {
    if (adjustSnapshotRef.current) {
      setLocalSkills(adjustSnapshotRef.current);
      adjustSnapshotRef.current = null;
    }
    setAdjustMode(false);
  }, []);

  const saveAdjustAndReturn = useCallback(() => {
    const snapshot = localSkillsRef.current;
    if (!snapshot.length) {
      adjustSnapshotRef.current = null;
      setAdjustMode(false);
      return;
    }
    const targetLevels = levelsWithoutUnlearned(levels);

    const next: LocalSkill[] = snapshot.map((s) => {
      const current_level = normalizeLevel(s.current_level, levels);
      let required_level = normalizeLevel(s.required_level, levels);
      if (String(required_level).toLowerCase() === 'unlearned')
        required_level = normalizeLevel(targetLevels[0] ?? s.required_level, levels);
      const cur = levelIndex(current_level, levels);
      const tgt = levelIndex(required_level, levels);
      const isGap = tgt > cur;
      return {
        ...s,
        current_level,
        required_level,
        original: {
          ...s.original,
          current_level,
          required_level,
          is_gap: isGap,
        },
      };
    });
    /* Synchronous commit so overview branch reads updated localSkills on same paint */
    flushSync(() => {
      setLocalSkills(next);
      setOverviewEpoch((e) => e + 1);
    });
    /* Persist so remount/re-enter doesn’t overwrite bars with stale API-only data */
    try {
      if (state?.goal && state?.learnerInformation) {
        const key = skillGapStorageKey(state.goal, state.learnerInformation);
        sessionStorage.setItem(
          key,
          JSON.stringify({
            goal: state.goal,
            skills: next.map((s) => ({
              name: s.original.skill_name || s.original.name,
              current_level: s.current_level,
              required_level: s.required_level,
              addToPlan: s.addToPlan,
            })),
          }),
        );
      }
    } catch {
      // ignore quota / private mode
    }
    adjustSnapshotRef.current = null;
    setAdjustMode(false);
  }, [levels, state?.goal, state?.learnerInformation]);

  useEffect(() => {
    // Wait for config so we use the correct level labels (backend uses lowercase like "unlearned")
    if (hasFiredRef.current || !config || !state?.goal || !state?.learnerInformation) return;

    // Prevent double-fire in the same mount (e.g. React StrictMode). Do NOT skip based on
    // sessionStorage: after navigating away and back, component remounts with empty state,
    // so we must call the API again to get skill gaps for the current goal.
    hasFiredRef.current = true;
    setIsLoading(true);
    setError(null);

    pushAppState('SkillGap → Received state', {
      goal: state.goal,
      personaKey: state.personaKey,
      learnerInformationLength: state.learnerInformation.length,
      learnerInformation: state.learnerInformation,
      isGoalManagementFlow: state.isGoalManagementFlow,
    });

    (async () => {
      try {
        const resp = (await identifySkillGapApi({
          learning_goal: state.goal,
          learner_information: state.learnerInformation,
        })) as unknown as Record<string, unknown>;

        setIdentifyResponse(resp);
        let rawGaps = (resp as any).skill_gaps;
        /* API may return { skill_gaps: [ ... ] } nested once */
        if (
          rawGaps &&
          typeof rawGaps === 'object' &&
          !Array.isArray(rawGaps) &&
          Array.isArray((rawGaps as Record<string, unknown>).skill_gaps)
        ) {
          rawGaps = (rawGaps as { skill_gaps: SkillGapItem[] }).skill_gaps;
        }
        const gapArray: SkillGapItem[] = Array.isArray(rawGaps)
          ? (rawGaps as SkillGapItem[])
          : rawGaps && typeof rawGaps === 'object'
          ? Object.values(rawGaps as Record<string, SkillGapItem>)
          : [];

        const normalizedGaps: SkillGapItem[] = gapArray.map((sg) => ({
          ...sg,
          skill_name: (sg.skill_name ?? sg.name ?? '').toString(),
        }));

        const targetLevels = levelsWithoutUnlearned(levels);
        const defaultRequired = targetLevels[0] ?? levels[1] ?? levels[0];

        const targetSources: Array<'backend' | 'default'> = [];

        const mapped = normalizedGaps.map((sg) => {
          const sgRec = sg as Record<string, unknown>;
          const rawCurrent = coerceLevelFromGap(sgRec, [
            'current_level',
            'observed_level',
            'current',
            'learner_level',
          ]);
          const rawRequired = coerceLevelFromGap(sgRec, [
            'required_level',
            'expected_level',
            'target_level',
          ]);
          const hasBackendTarget =
            Boolean(rawRequired && String(rawRequired).trim()) ||
            Boolean(sg.required_level && String(sg.required_level).trim());
          let required_level = normalizeLevel(rawRequired || sg.required_level || defaultRequired, levels);
          if (String(required_level).toLowerCase() === 'unlearned')
            required_level = normalizeLevel(defaultRequired, levels);
          targetSources.push(hasBackendTarget ? 'backend' : 'default');
          /* Only fall back to levels[0] when backend sent no usable current — keeps bars valid */
          const current_level = rawCurrent
            ? normalizeLevel(rawCurrent, levels)
            : normalizeLevel(sg.current_level ?? levels[0], levels);
          return {
            original: { ...sg, current_level: rawCurrent || sg.current_level, required_level: rawRequired || sg.required_level },
            current_level,
            required_level,
            addToPlan: sg.is_gap !== false,
          };
        });

        try {
          if (state?.goal && state?.learnerInformation) {
            pushAppState('SkillGap → Required level source', {
              goal: state.goal,
              learnerInformationLength: state.learnerInformation.length,
              levelsConfig: levels,
              skills: mapped.map((m, idx) => ({
                name:
                  (m.original.skill_name as string | undefined) ||
                  (m.original.name as string | undefined) ||
                  `Skill ${idx + 1}`,
                required_level: m.required_level,
                source: targetSources[idx] ?? 'default',
              })),
            });
          }
        } catch {
          // debug-only; ignore
        }

        /* Re-apply saved adjust by skill name (order-safe) */
        try {
          if (state?.goal && state?.learnerInformation) {
            const key = skillGapStorageKey(state.goal, state.learnerInformation);
            const raw = sessionStorage.getItem(key);
            if (raw) {
              const parsed = JSON.parse(raw) as { goal?: string; skills?: SavedSkill[] };
              if (parsed.goal === state.goal && Array.isArray(parsed.skills)) {
                applySavedSkillsToMapped(mapped, parsed.skills, levels);
              }
            }
          }
        } catch {
          // ignore bad JSON
        }

        setLocalSkills(mapped);

        try {
          const biasData = (await auditSkillGapBiasApi({
            // Backend expects JSON string under `skill_gaps`
            skill_gaps: JSON.stringify({ skill_gaps: normalizedGaps }),
            learner_information: state.learnerInformation,
          })) as Record<string, unknown>;
          setBiasAudit(biasData);
        } catch {
          // ignore bias audit errors
        }
      } catch {
        setError('Failed to identify skill gaps. Please try again.');
      } finally {
        setIsLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const handleToggle = useCallback((idx: number) => {
    setLocalSkills((prev) => prev.map((s, i) => (i === idx ? { ...s, addToPlan: !s.addToPlan } : s)));
  }, []);

  const handleTargetChange = useCallback(
    (idx: number, level: string) => {
      const targetLevels = levelsWithoutUnlearned(levels);
      const normalized =
        String(level).toLowerCase() === 'unlearned'
          ? normalizeLevel(targetLevels[0] ?? level, levels)
          : normalizeLevel(level, levels);
      setLocalSkills((prev) =>
        prev.map((s, i) =>
          i === idx
            ? {
                ...s,
                required_level: normalized,
                // If user manually adjusts target, treat it as intentional gap tracking
                addToPlan: true,
              }
            : s,
        ),
      );
    },
    [levels],
  );

  const handleCurrentChange = useCallback(
    (idx: number, level: string) => {
      setLocalSkills((prev) =>
        prev.map((s, i) => {
          if (i !== idx) return s;
          const normalized = normalizeLevel(level, levels);
          const curIdx = levelIndex(normalized, levels);
          const reqIdx = levelIndex(s.required_level, levels);
          return {
            ...s,
            current_level: normalized,
            addToPlan: curIdx >= reqIdx ? false : s.addToPlan,
          };
        }),
      );
    },
    [levels],
  );

  const plannedSkills = localSkills.filter((s) => s.addToPlan);
  const hasGaps = plannedSkills.some(
    (s) => levelIndex(s.required_level, levels) > levelIndex(s.current_level, levels),
  );
  const selectedCount = plannedSkills.length;
  const identifiedCount = localSkills.length;

  const goalAssessment = (identifyResponse?.goal_assessment as Record<string, unknown> | undefined) ?? null;
  const refinedGoal = (goalAssessment?.refined_goal as string | undefined) ?? state?.goal ?? '';
  const retrievedSources = (identifyResponse?.retrieved_sources as unknown[] | undefined) ?? [];
  void goalAssessment?.auto_refined;
  void biasAudit;

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

      pushAppState('SkillGap → Create profile', {
        userId,
        goal: refinedGoal,
        personaKey: state.personaKey,
        learnerInformation: state.learnerInformation,
        selectedSkillCount: filteredGaps.length,
        skillNames: filteredGaps.map((g) => (g as any).skill_name || (g as any).name || '?'),
      });

      const profileResult = await createProfileMutation.mutateAsync({
        learning_goal: refinedGoal,
        learner_information: state.learnerInformation,
        skill_gaps: skillGapsToPythonLiteral(filteredGaps),
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
        goal_context: (identifyResponse as any)?.goal_context,
        retrieved_sources: retrievedSources,
        bias_audit: biasAudit,
        profile_fairness: profileFairness,
        learner_profile: learnerProfile,
      });

      try {
        await syncProfileApi(userId, newGoal.id);
      } catch {
        // ignore sync errors here
      }

      refreshGoals();
      setSelectedGoalId(newGoal.id);
      /* Clear draft adjust so next visit gets fresh API state unless user adjusts again */
      try {
        if (state.goal && state.learnerInformation) {
          sessionStorage.removeItem(skillGapStorageKey(state.goal, state.learnerInformation));
        }
      } catch {
        // ignore
      }
      navigate('/learning-path');
    } catch {
      setError('Failed to create your learning path. Please try again.');
    } finally {
      setIsScheduling(false);
    }
  }, [
    userId,
    state,
    plannedSkills,
    refinedGoal,
    goalAssessment,
    identifyResponse,
    retrievedSources,
    biasAudit,
    createProfileMutation,
    validateFairnessMutation,
    refreshGoals,
    setSelectedGoalId,
    navigate,
  ]);

  if (!state?.goal) return null;

  if (isLoading && !identifyResponse) {
    return (
      <PathGenerationLoading
        title={SKILL_GAP_LOADING.title}
        subtitle={SKILL_GAP_LOADING.subtitle}
        steps={SKILL_GAP_LOADING.steps}
        tips={SKILL_GAP_LOADING.tips}
        goalTitle={state.goal}
      />
    );
  }

  if (error && !identifyResponse) {
    return (
      <div className="max-w-3xl space-y-4">
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">{error}</div>
        <Button variant="secondary" onClick={() => navigate('/onboarding')}>
          Back to Onboarding
        </Button>
      </div>
    );
  }

  if (isScheduling) {
    return (
      <PathGenerationLoading
        title={LEARNING_PATH_LOADING.title}
        steps={LEARNING_PATH_LOADING.steps}
        tips={LEARNING_PATH_LOADING.tips}
        goalTitle={refinedGoal || state?.goal || ''}
      />
    );
  }

  /* ---------- Default overview: summary cards + CTA; link opens detailed adjust UI ---------- */
  const gapLv = (s: LocalSkill) => {
    const cur = levelIndex(s.current_level, levels);
    const tgt = levelIndex(s.required_level, levels);
    return Math.max(0, tgt - cur);
  };
  const priorityGapCount = localSkills.filter((s) => s.addToPlan && gapLv(s) >= 1).length;

  if (!adjustMode && localSkills.length > 0) {
    const selected = localSkills[selectedSkillIdx] ?? localSkills[0];
    const selectedName =
      selected.original.skill_name || selected.original.name || `Skill ${selectedSkillIdx + 1}`;
    const reason = stringFromBackend(selected.original.reason);
    const levelConfidence = stringFromBackend(selected.original.level_confidence);
    const suggestedPath = stringFromBackend(
      (selected.original as Record<string, unknown>).suggested_growth_path,
    );
    /*
     * Focus areas list only when backend sends suggested_growth_path (multi-part).
     * Do not split reason into bullets — same text is already shown above as paragraph;
     * splitting duplicated the assessment (e.g. one sentence as <p> and again as <li>).
     */
    const bullets: string[] = suggestedPath
      ? suggestedPath
          .split(/\n|;|；/)
          .map((s) => s.trim())
          .filter(Boolean)
          /* Drop any bullet that is the same as reason (no duplicate) */
          .filter((b) => {
            if (!reason) return true;
            const r = reason.replace(/\s+/g, ' ').trim().toLowerCase();
            const bb = b.replace(/\s+/g, ' ').trim().toLowerCase();
            if (bb === r || r === bb) return false;
            if (r.length > 20 && bb.length > 20 && (r.includes(bb) || bb.includes(r))) return false;
            return true;
          })
      : [];

    const confidenceLabel =
      levelConfidence === 'high'
        ? 'High'
        : levelConfidence === 'medium'
          ? 'Med'
          : levelConfidence === 'low'
            ? 'Low'
            : levelConfidence || '—';

    return (
      <div
        key={overviewEpoch}
        className="mx-auto w-full max-w-7xl bg-[#F6FAFB] px-4 py-6 sm:px-6 lg:px-8 lg:pb-10"
      >
        <header className="mb-4">
          <h1 className="text-xl font-bold text-[#16324A] sm:text-2xl">Skill gap analysis</h1>
          <p className="mt-1 text-sm text-[#5F7486]">
            Click any skill to view details and adjust levels.
          </p>
          <p className="mt-2 text-sm font-medium text-[#16324A]">
            {localSkills.length} core competencies
            {priorityGapCount > 0 && (
              <span className="ml-2 font-normal text-[#5F7486]">
                ({priorityGapCount} priority gap{priorityGapCount !== 1 ? 's' : ''} to close first)
              </span>
            )}
          </p>
        </header>

        <div className="grid gap-6 lg:grid-cols-2 lg:items-start lg:gap-8 lg:pb-2">
          {/* ---------- Left: skill gap analysis list ---------- */}
          <div className="min-w-0">
            <ul className="min-w-0 space-y-2">
              {localSkills.map((skill, idx) => {
                const name = skill.original.skill_name || skill.original.name || `Skill ${idx + 1}`;
                const g = gapLv(skill);
                const isSelected = idx === selectedSkillIdx;
                const currentLabel =
                  skill.current_level && String(skill.current_level).trim()
                    ? formatLevelLabel(skill.current_level)
                    : '—';
                const chip =
                  g >= 3
                    ? { text: 'Major gap', className: 'bg-red-50 text-red-700 border border-red-100' }
                    : g === 2
                      ? { text: 'Moderate gap', className: 'bg-[#E8F8F1] text-[#217A57] border border-[#BFE7D3]' }
                      : g === 1
                        ? { text: 'Slight gap', className: 'bg-[#FFF4DB] text-[#9A6B00] border border-[#F3DFB2]' }
                        : { text: 'On target', className: 'bg-[#E8F7FA] text-[#5F7486] border border-[#D7E3E8]' };

                return (
                  <li key={`${name}-${idx}-${skill.current_level}-${skill.required_level}-${skill.addToPlan}`}>
                    <button
                      type="button"
                      onClick={() => setSelectedSkillIdx(idx)}
                      className={cn(
                        'flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left transition-colors',
                        isSelected
                          ? 'border-[#8FC7D1] bg-[#F7FBFC]'
                          : 'border-[#DCE7EA] bg-white hover:border-[#B8D4DC] hover:bg-[#F6FAFB]',
                      )}
                    >
                      <span
                        className={cn(
                          'flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold',
                          isSelected
                            ? 'bg-[#3AA6B9] text-white'
                            : 'bg-[#E8F0F2] text-[#5F7486]',
                        )}
                      >
                        {idx + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold text-[#16324A] truncate">{name}</p>
                        <p className="text-[11px] text-[#7E92A3]">
                          {currentLabel} → {formatLevelLabel(skill.required_level)}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <span
                          className={cn(
                            'rounded-full px-2 py-0.5 text-[10px] font-medium',
                            chip.className,
                          )}
                        >
                          {chip.text}
                        </span>
                        {!skill.addToPlan && (
                          <span className="text-[10px] font-medium text-slate-400">skipped</span>
                        )}
                        <svg
                          className={cn(
                            'h-4 w-4 shrink-0 text-[#7E92A3] transition-transform',
                            isSelected && 'text-[#3AA6B9]',
                          )}
                          fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* ---------- Right column: aside + actions ---------- */}
          <div className="flex min-w-0 flex-col gap-4">
            <div className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-24 lg:self-start">
            <aside className="min-w-0 rounded-2xl border border-[#DCE7EA] bg-white p-6 shadow-[0_1px_3px_rgba(22,50,74,0.06)]">
              {/* Skill name + gap toggle */}
              <div className="flex items-start justify-between gap-3 mb-4">
                <h2 className="text-lg font-bold text-[#16324A] min-w-0 break-words">{selectedName}</h2>
                <Toggle
                  label="Gap"
                  checked={selected.addToPlan}
                  onChange={() => handleToggle(selectedSkillIdx)}
                  className="shrink-0 [&_span]:text-xs [&_span]:text-[#5F7486]"
                />
              </div>

              {reason && (
                <p className="mb-4 text-sm leading-relaxed break-words overflow-hidden text-[#16324A]">{reason}</p>
              )}

              {/* Inline level adjustment tracks */}
              <div className="space-y-5 border-y border-[#D7E3E8] py-4">
                <LevelTrackRow
                  variant="target"
                  rowLabel="Required level"
                  value={selected.required_level}
                  levels={levelsWithoutUnlearned(levels)}
                  onChange={(level) => handleTargetChange(selectedSkillIdx, level)}
                />
                <LevelTrackRow
                  variant="current"
                  rowLabel="Current level"
                  value={selected.current_level}
                  levels={levels}
                  onChange={(level) => handleCurrentChange(selectedSkillIdx, level)}
                />
              </div>

              {/* Stats row */}
              <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                <div>
                  <p className="text-lg font-bold tabular-nums text-[#16324A]">{gapLv(selected)}</p>
                  <p className="text-[10px] font-medium uppercase tracking-wider text-[#7E92A3]">Level gap</p>
                </div>
                <div>
                  <p className="text-lg font-bold text-[#16324A]">{confidenceLabel}</p>
                  <p className="text-[10px] font-medium uppercase tracking-wider text-[#7E92A3]">Confidence</p>
                </div>
                <div>
                  <p className="text-lg font-bold text-[#16324A]">{selected.addToPlan ? 'Yes' : 'No'}</p>
                  <p className="text-[10px] font-medium uppercase tracking-wider text-[#7E92A3]">In plan</p>
                </div>
              </div>

              {bullets.length > 0 && (
                <div className="mt-4">
                  <p className="mb-2 text-xs font-semibold text-[#16324A]">Focus areas (from analysis)</p>
                  <ul className="list-inside list-disc space-y-1 break-words text-sm text-[#5F7486]">
                    {bullets.slice(0, 6).map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                </div>
              )}
            </aside>

            {/* Same sticky group as aside — avoids overlap when main scrolls */}
            <div className="flex w-full flex-col gap-3">
              <Button
                size="lg"
                className="relative z-10 w-full justify-center gap-2 bg-[#63B3C1] text-white hover:bg-[#529EAC] active:bg-[#4A8F9C] focus-visible:ring-[#3AA6B9]"
                onClick={handleSchedule}
                loading={isScheduling}
                disabled={plannedSkills.length === 0 || !hasGaps || isScheduling}
              >
                {isScheduling ? 'Creating…' : 'Generate learning path'}
              </Button>
              {/* "Adjust levels manually" hidden — inline adjustment now lives in the aside panel */}
              <button
                type="button"
                className="relative z-10 w-full text-center text-sm font-medium text-[#5F7486] underline decoration-[#DCE7EA] underline-offset-2 hover:text-[#3AA6B9]"
                onClick={() => navigate('/onboarding')}
              >
                Change my learning goal
              </button>
            </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-7xl bg-[#F6FAFB] px-4 py-6 sm:px-6 lg:px-8">
      <div className="max-w-5xl space-y-6 pb-28">
      <button
        type="button"
        className="text-sm font-medium text-[#5F7486] underline decoration-[#DCE7EA] underline-offset-2 hover:text-[#3AA6B9]"
        onClick={saveAdjustAndReturn}
      >
        ← Back to Skill gap analysis
      </button>

      <div className="space-y-1">
        <p className="text-sm font-medium text-[#16324A]">Select the skills you want included in your learning plan.</p>
        <p className="text-sm font-medium text-[#5F7486]">
          {identifiedCount} identified • {selectedCount} selected
        </p>
      </div>

      <div className="space-y-4">
        {localSkills.map((skill, idx) => (
          <SkillCard
            key={`${skill.original.skill_name ?? skill.original.name ?? 'skill'}-${idx}`}
            index={idx}
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
        <details className="text-sm rounded-lg border border-[#DCE7EA] bg-white">
          <summary className="px-4 py-3 cursor-pointer font-medium text-[#16324A] select-none">
            Retrieved sources ({retrievedSources.length})
          </summary>
          <ul className="list-inside list-disc space-y-1 px-4 pt-1 pb-4 text-xs text-[#5F7486]">
            {retrievedSources.slice(0, 5).map((src, i) => (
              <li key={i}>{typeof src === 'string' ? src : JSON.stringify(src)}</li>
            ))}
          </ul>
        </details>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">{error}</div>
      )}
      </div>

      {/* Floating bottom action bar — only over main column (same left offset as sidenav), not over sidenav */}
      <div
        className={cn(
          'fixed bottom-0 right-0 z-50 h-[70px] border-t border-[#DCE7EA] bg-transparent shadow-[0_-4px_24px_rgba(22,50,74,0.06)]',
          collapsed ? 'left-16' : 'left-[15rem]',
        )}
      >
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 bg-[rgba(255,255,255,0.92)] px-4 py-3 sm:px-6 lg:px-8">
          <Button type="button" variant="secondary" onClick={cancelAdjust}>
            Cancel
          </Button>
          <Button
            type="button"
            size="lg"
            onClick={saveAdjustAndReturn}
            className="bg-[#63B3C1] px-6 text-white hover:bg-[#529EAC] active:bg-[#4A8F9C] focus-visible:ring-[#3AA6B9] sm:px-8"
          >
            Save Changes and Return
          </Button>
        </div>
      </div>
    </div>
  );
}

