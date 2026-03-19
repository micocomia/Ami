import { useState, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, InputField } from '@/components/ui';
import { cn } from '@/lib/cn';
import { useHasEnteredGoal } from '@/context/HasEnteredGoalContext';
import { usePersonas } from '@/api/endpoints/config';
import { useExtractPdfText } from '@/api/endpoints/pdf';
import { pushAppState } from '@/components/DebugPanel';
import LogoBlack from '@/assets/Logo_black.png';
import {
  setLearningStylePreference,
  withLearningStyleInLearnerInformation,
  type LearningStyleOption,
} from '@/lib/learningStylePreference';
import { clearStoredResume, setStoredResume } from '@/lib/resumeStorage';

/* ------------------------------------------------------------------ */
/*  Mock data                                                         */
/* ------------------------------------------------------------------ */

interface Category {
  id: string;
  label: string;
}

const CATEGORIES: Category[] = [
  { id: 'language', label: 'Language learning' },
  { id: 'coding', label: 'Coding & tech' },
  { id: 'career', label: 'Career growth' },
  { id: 'design', label: 'Design & creativity' },
];

interface LearningPreference {
  id: string;
  title: string;
  description: string;
  tags: string[];
}

const LEARNING_PREFERENCES: LearningPreference[] = [
  {
    id: 'hands-on',
    title: 'Interactive',
    description: 'You learn fastest by trying things directly: short exercises, guided practice, and immediate feedback.',
    tags: ['Active', 'Visual', 'Step-by-step'],
  },
  {
    id: 'reflective',
    title: 'Textual',
    description: 'You prefer reading clear explanations first, then reflecting before applying what you learned.',
    tags: ['Reading', 'Reflection'],
  },
  {
    id: 'visual',
    title: 'Visual',
    description: 'You understand ideas better with diagrams, examples, and visual breakdowns instead of long text.',
    tags: ['Visual', 'Diagrams'],
  },
  {
    id: 'conceptual',
    title: 'Concise',
    description: 'You prefer key concepts and big-picture structure first, then only the most important details.',
    tags: ['Theory', 'Analysis', 'Big-picture'],
  },
  {
    id: 'balanced',
    title: 'Balanced',
    description: 'You want a mix: concise explanations, practical exercises, and visuals depending on the topic.',
    tags: ['Flexible', 'Neutral'],
  },
];

/** Map frontend preference id → backend persona key (GET /personas returns full names) */
const PREFERENCE_TO_PERSONA: Record<string, string> = {
  'hands-on': 'Hands-on Explorer',
  reflective: 'Reflective Reader',
  visual: 'Visual Learner',
  conceptual: 'Conceptual Thinker',
  balanced: 'Balanced Learner',
};

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function OnboardingPage() {
  const navigate = useNavigate();
  const { setHasEnteredGoal } = useHasEnteredGoal();
  const { data: personasData } = usePersonas();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const extractPdf = useExtractPdfText();
  const [step, setStep] = useState<1 | 2 | 3>(1);

  // Step 1: goal category + input description can be used together.
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [goalDetails, setGoalDetails] = useState('');

  const [isSubmitting, setIsSubmitting] = useState(false);

  // Step 2: learning style selection (5 options).
  /** Default to balanced for faster course load than visual. */
  const [selectedPreferenceId, setSelectedPreferenceId] = useState<string | null>('balanced');

  // Step 3: optional resume upload.
  const [resumeText, setResumeText] = useState('');
  const [resumeFileName, setResumeFileName] = useState<string | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const personas = personasData?.personas ?? {};

  const CATEGORY_TO_PREFIX: Record<string, string> = useMemo(
    () => ({
      language: 'I want to learn a new language：',
      coding: 'I want to learn Python for beginners：',
      career: 'I want to prepare for interviews：',
      design: 'I want to improve my design skills：',
    }),
    [],
  );

  const composedLearningGoal = useMemo(() => {
    const details = goalDetails.trim();
    if (!selectedCategory) return details;
    const prefix = CATEGORY_TO_PREFIX[selectedCategory] ?? '';
    if (!prefix) return details;
    if (!details) return prefix;
    return `${prefix}${details}`;
  }, [CATEGORY_TO_PREFIX, goalDetails, selectedCategory]);

  const canContinueStep1 = Boolean(goalDetails.trim()) || selectedCategory !== null;

  const handleSelectCategory = useCallback(
    (id: string) => {
      const next = selectedCategory === id ? null : id;
      setSelectedCategory(next);
      if (!next) {
        setGoalDetails('');
        return;
      }
      setGoalDetails(CATEGORY_TO_PREFIX[next] ?? '');
    },
    [CATEGORY_TO_PREFIX, selectedCategory],
  );

  const handleBeginLearning = useCallback(() => {
    const trimmed = composedLearningGoal.trim();
    if (!trimmed) return;
    const prefId = selectedPreferenceId ?? 'balanced';
    const personaKey = PREFERENCE_TO_PERSONA[prefId] ?? prefId;
    // Build learnerInformation similar to old frontend: persona + optional resume summary
    let learnerInformation = resumeText;
    if (personas[personaKey]) {
      const dims = personas[personaKey].fslsm_dimensions;
      const dimStr = Object.entries(dims)
        .map(([k, v]) => `${k}=${v}`)
        .join(', ');
      learnerInformation = `Learning Persona: ${personaKey} (initial FSLSM: ${dimStr}). ${learnerInformation}`;
    }
    // Ensure learnerInformation is never empty so SkillGapPage's guard passes
    if (!learnerInformation) {
      learnerInformation = `Learning goal: ${trimmed}.`;
    }
    // Sync onboarding persona choice → Profile "Learning style" localStorage
    const selectedTitle =
      LEARNING_PREFERENCES.find((p) => p.id === prefId)?.title ?? 'Balanced';
    setLearningStylePreference(selectedTitle as LearningStyleOption);
    // Persisted Profile learning style → included for create-learner-profile / path pipeline
    learnerInformation = withLearningStyleInLearnerInformation(learnerInformation);
    pushAppState('Onboarding → Submit', {
      goal: trimmed,
      personaKey,
      learningStyle: selectedTitle,
      hasResume: Boolean(resumeText),
      resumeTextLength: resumeText.length,
      learnerInformation,
    });
    setIsSubmitting(true);
    setHasEnteredGoal(true);
    navigate('/skill-gap', {
      state: {
        goal: trimmed,
        personaKey,
        learnerInformation,
        isGoalManagementFlow: false,
      },
    });
  }, [
    composedLearningGoal,
    selectedPreferenceId,
    personas,
    resumeText,
    navigate,
    setHasEnteredGoal,
  ]);

  const handleSkipResume = useCallback(() => {
    setResumeError(null);
    setResumeText('');
    setResumeFileName(null);
    clearStoredResume();
  }, []);

  const stepItems = [
    { n: 1, label: 'What do you want to learn?' },
    { n: 2, label: 'How do you learn best?' },
    { n: 3, label: 'Upload resume' },
  ] as const;

  return (
    <div className="flex flex-col min-h-0 flex-1">
      {/* ── Scrollable content ── */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {/* ── Hero ── */}
        <section className="text-center pt-12 pb-6 px-4">
          <div className="flex justify-center">
            <img
              src={LogoBlack}
              alt="Ami"
              className="h-14 sm:h-16 md:h-20 w-auto max-w-full object-contain"
            />
          </div>
          <p className="mt-3 text-lg text-slate-400 font-medium">
            Your Adaptive Learning Companion
          </p>
        </section>
        {/* ── 3-step wizard ── */}
        <section className="max-w-5xl w-full mx-auto px-4 space-y-8 pb-12">
          {/* Top steps indicator */}
          <div className="pt-2">
            <div className="flex items-center justify-center gap-0">
              {stepItems.map((s, idx) => {
                const state = s.n < step ? 'done' : s.n === step ? 'active' : 'todo';
                const isDone = state === 'done';
                const isActive = state === 'active';
                const circleClass = cn(
                  'flex items-center justify-center w-9 h-9 rounded-full text-sm font-bold border',
                  isDone
                    ? 'bg-[#78B3BA] border-[#78B3BA] text-white'
                    : isActive
                      ? 'bg-white border-[#78B3BA] text-[#78B3BA]'
                      : 'bg-slate-100 border-slate-200 text-slate-400',
                );
                const labelClass = cn(
                  'hidden sm:block text-xs font-medium',
                  isDone ? 'text-slate-600' : isActive ? 'text-[#78B3BA]' : 'text-slate-400',
                );

                return (
                  <div key={s.n} className="flex items-center gap-3">
                    <div className={circleClass} aria-current={isActive ? 'step' : undefined}>
                      {isDone ? (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M20 6L9 17l-5-5" />
                        </svg>
                      ) : (
                        s.n
                      )}
                    </div>
                    <div className={labelClass}>{s.label}</div>
                    {idx < stepItems.length - 1 && (
                      <div
                        className={cn(
                          'h-[2px] w-10',
                          isDone ? 'bg-[#78B3BA]' : 'bg-slate-200',
                        )}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Step 1 */}
          {step === 1 && (
            <div className="space-y-8">
              <p className="text-center text-sm font-medium text-slate-700">What do you want to learn?</p>

              <div className="w-full max-w-4xl mx-auto">
                <InputField
                  placeholder="What do you want to learn? e.g. conversational English, Python, interview skills, UX design"
                  value={goalDetails}
                  onChange={(e) => setGoalDetails(e.target.value)}
                  disabled={isSubmitting}
                  className="custom-input w-full h-[56px]"
                />
              </div>

              <div className="space-y-3">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {CATEGORIES.map((cat) => {
                    const isSelected = selectedCategory === cat.id;
                    return (
                      <button
                        key={cat.id}
                        type="button"
                        onClick={() => handleSelectCategory(cat.id)}
                        disabled={isSubmitting}
                        className={cn(
                          'suggestion-card py-4 px-3 rounded-xl flex items-center justify-center text-center disabled:opacity-50 disabled:cursor-not-allowed',
                          isSelected && 'active',
                        )}
                      >
                        <span className="text-[12px] font-bold leading-tight">{cat.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex justify-center pt-2">
                <Button
                  size="lg"
                  onClick={() => setStep(2)}
                  disabled={!canContinueStep1 || isSubmitting}
                  className="w-full sm:w-auto rounded-full !bg-[#78B3BA] hover:!bg-[#6aa3aa] !text-white px-10 py-4 text-lg font-semibold shadow-xl shadow-teal-500/20"
                >
                  Continue
                </Button>
              </div>
            </div>
          )}

          {/* Step 2 */}
          {step === 2 && (
            <div className="space-y-8">
              <p className="text-center text-sm font-medium text-slate-700">How do you learn best?</p>

              <div
                role="radiogroup"
                aria-label="Learning style options"
                className="max-w-3xl mx-auto overflow-hidden rounded-2xl border border-slate-200 bg-white"
              >
                {LEARNING_PREFERENCES.map((pref) => {
                  const selected = selectedPreferenceId === pref.id;
                  return (
                    <button
                      key={pref.id}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => setSelectedPreferenceId(pref.id)}
                      disabled={isSubmitting}
                      className={cn(
                        'w-full border-b border-slate-200 px-5 py-4 text-left transition-colors last:border-b-0',
                        selected
                          ? 'bg-[#f0f9fa]'
                          : 'bg-white hover:bg-slate-50',
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <span
                          className={cn(
                            'mt-1 inline-flex h-4 w-4 items-center justify-center rounded-full border',
                            selected ? 'border-[#78B3BA]' : 'border-slate-300',
                          )}
                        >
                          {selected && (
                            <span className="block h-2 w-2 rounded-full bg-[#78B3BA]" />
                          )}
                        </span>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="font-bold text-slate-900">{pref.title}</p>
                          </div>
                          <p className="mt-1 text-sm text-slate-500 leading-relaxed">{pref.description}</p>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="flex justify-center pt-2">
                <Button
                  size="lg"
                  onClick={() => setStep(3)}
                  disabled={!selectedPreferenceId || isSubmitting}
                  className="w-full sm:w-auto rounded-full !bg-[#78B3BA] hover:!bg-[#6aa3aa] !text-white px-10 py-4 text-lg font-semibold shadow-xl shadow-teal-500/20"
                >
                  Continue
                </Button>
              </div>
            </div>
          )}

          {/* Step 3 */}
          {step === 3 && (
            <div className="space-y-8">
              <div className="space-y-2 text-center">
                <p className="text-sm font-medium text-slate-700">Upload resume</p>
                <p className="text-xs text-slate-500">
                  Upload your resume so Ami can identify your skill gaps and tailor your learning path.
                </p>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  e.target.value = '';
                  if (!file) return;
                  setResumeError(null);
                  setResumeFileName(file.name);
                  try {
                    const result = await extractPdf.mutateAsync(file);
                    const pdfText = (result as { text?: string }).text ?? '';
                    if (!pdfText) {
                      setResumeError('Could not read PDF. Please try another file.');
                      setResumeFileName(null);
                      return;
                    }
                    const resumeContent = `Resume summary: ${pdfText}`;
                    setResumeText(resumeContent);
                    setStoredResume(file.name, resumeContent);
                  } catch {
                    setResumeError('Upload failed. Please try again.');
                    setResumeFileName(null);
                    setResumeText('');
                  }
                }}
              />

              <div className="max-w-3xl mx-auto">
                {!resumeFileName ? (
                  <button
                    type="button"
                    disabled={isSubmitting || extractPdf.isPending}
                    onClick={() => fileInputRef.current?.click()}
                    className={cn(
                      'w-full rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors',
                      'border-slate-200 hover:border-[#78B3BA] hover:bg-[#f0f9fa]',
                    )}
                  >
                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">
                      {extractPdf.isPending ? 'Reading resume…' : 'Click to upload your resume (.pdf)'}
                    </p>
                  </button>
                ) : (
                  <div className="rounded-2xl border border-[#BFE7D3] bg-[#E8F8F1] px-6 py-4">
                    <div className="flex items-center gap-4">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#78B3BA]/15">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#78B3BA" strokeWidth="3">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M20 6L9 17l-5-5" />
                        </svg>
                      </div>
                      <div className="min-w-0">
                        <p className="font-bold text-slate-900 truncate">{resumeFileName}</p>
                        <p className="text-sm text-slate-600">Ready to personalise your path</p>
                      </div>
                    </div>
                    {resumeError && <p className="text-xs text-red-500 mt-2">{resumeError}</p>}
                  </div>
                )}
                {resumeError && !resumeFileName && (
                  <p className="text-xs text-red-500 mt-2 text-center">{resumeError}</p>
                )}
              </div>

              <div className="flex items-center justify-center">
                <button
                  type="button"
                  className="text-sm font-medium text-[#5F7486] underline decoration-[#DCE7EA] underline-offset-2 hover:text-[#3AA6B9]"
                  onClick={handleSkipResume}
                  disabled={isSubmitting || extractPdf.isPending}
                >
                  Skip for now
                </button>
              </div>

              <div className="flex justify-center pt-1">
                <Button
                  size="lg"
                  onClick={handleBeginLearning}
                  loading={false}
                  disabled={isSubmitting || !composedLearningGoal.trim()}
                  className="w-full sm:w-auto rounded-full !bg-[#78B3BA] hover:!bg-[#6aa3aa] !text-white px-10 py-4 text-lg font-semibold shadow-xl shadow-teal-500/20"
                >
                  Begin learning &rarr;
                </Button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
