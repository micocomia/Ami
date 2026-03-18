import { useState, useCallback, useRef } from 'react';
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
import { setStoredResume } from '@/lib/resumeStorage';

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
    description: 'Learns best by doing and practicing with examples.',
    tags: ['Active', 'Visual', 'Step-by-step'],
  },
  {
    id: 'reflective',
    title: 'Textual',
    description: 'Learns through reading and reflection. Prefers detailed explanations.',
    tags: ['Reading', 'Reflection'],
  },
  {
    id: 'visual',
    title: 'Visual',
    description: 'Understands concepts best through visuals and diagrams.',
    tags: ['Visual', 'Diagrams'],
  },
  {
    id: 'conceptual',
    title: 'Concise',
    description: 'Enjoys big-picture ideas, theory, and analysis.',
    tags: ['Theory', 'Analysis', 'Big-picture'],
  },
  {
    id: 'balanced',
    title: 'Balanced',
    description: 'Flexible across different learning formats.',
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

type OnboardingState = 'idle' | 'category-selected' | 'goal-entered' | 'submitting';

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function OnboardingPage() {
  const navigate = useNavigate();
  const { setHasEnteredGoal } = useHasEnteredGoal();
  const { data: personasData } = usePersonas();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const extractPdf = useExtractPdfText();
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [learningGoal, setLearningGoal] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  /** Default persona when user does not choose — balanced for faster course load than visual */
  const [selectedPreferenceId, setSelectedPreferenceId] = useState<string | null>('balanced');
  const [resumeText, setResumeText] = useState('');
  const [resumeFileName, setResumeFileName] = useState<string | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const personas = personasData?.personas ?? {};

  const pageState: OnboardingState = isSubmitting
    ? 'submitting'
    : learningGoal.trim()
      ? 'goal-entered'
      : selectedCategory !== null
        ? 'category-selected'
        : 'idle';

  const handleSelectCategory = useCallback(
    (id: string) => {
      const next = selectedCategory === id ? null : id;
      setSelectedCategory(next);

      if (!next) {
        setLearningGoal('');
        return;
      }

      const mapped: Record<string, string> = {
        language: 'I want to learn a new language：',
        coding: 'I want to learn Python for beginners：',
        career: 'I want to prepare for interviews：',
        design: 'I want to improve my design skills：',
      };

      setLearningGoal(mapped[next] ?? '');
    },
    [selectedCategory],
  );

  const handleBeginLearning = useCallback(() => {
    const trimmed = learningGoal.trim();
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
  }, [learningGoal, selectedPreferenceId, personas, resumeText, navigate, setHasEnteredGoal]);

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
        {/* ── Main content (goal + categories + preferences) ── */}
        <section className="max-w-5xl w-full mx-auto px-4 space-y-8 pb-12">
          {/* Main prompt */}
          <p className="text-center text-sm font-medium text-slate-700">What would you like to learn today?</p>

          {/* Goal input */}
          <div className="flex w-full flex-col gap-2">
            <div className="w-full max-w-4xl mx-auto">
              <InputField
                placeholder="What do you want to learn? e.g. conversational English, Python, interview skills, UX design"
                value={learningGoal}
                onChange={(e) => setLearningGoal(e.target.value)}
                disabled={isSubmitting}
                className="custom-input w-full h-[56px]"
              />
            </div>
          </div>

          {/* Suggested quick topics */}
          <div className="space-y-4">
           
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

          {/* Learning style preferences */}
          <div className="mt-6 space-y-4">
            <div className="text-center space-y-1">
              <p className="text-[10px] font-bold text-slate-300 uppercase tracking-[0.2em]">
                Learning Style
              </p>
            </div>

            {/* Preference tabs */}
            <div className="segmented-control flex w-full max-w-xl mx-auto">
              {LEARNING_PREFERENCES.map((pref) => {
                const isSelected = selectedPreferenceId === pref.id;
                return (
                  <button
                    key={pref.id}
                    type="button"
                    onClick={() => setSelectedPreferenceId(pref.id)}
                    disabled={isSubmitting}
                    className={cn(
                      'segmented-item flex-1 py-2.5 rounded-xl uppercase tracking-[0.18em] text-center disabled:opacity-50 disabled:cursor-not-allowed',
                      isSelected && 'active',
                    )}
                  >
                    {pref.title}
                  </button>
                );
              })}
            </div>

            {/* Selected preference detail card (defaults to Balanced — faster course load than visual) */}
            {selectedPreferenceId && (() => {
              const selected =
                LEARNING_PREFERENCES.find((p) => p.id === selectedPreferenceId) ?? LEARNING_PREFERENCES[0];
              return (
                <div
                  id="styleDetailCard"
                  className="mt-3 max-w-xl mx-auto text-left bg-slate-50/50 rounded-r-xl px-6 py-4"
                >
                  <div className="flex justify-between items-start mb-1">
                    <p className="text-sm font-bold text-slate-800">{selected.title}</p>
                    <div className="flex gap-1">
                      {selected.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-[9px] font-bold text-teal/60 uppercase"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                  <p className="text-xs text-slate-500 leading-relaxed">{selected.description}</p>
                </div>
              );
            })()}
          </div>
        </section>

        {/* ── Bottom action bar：secondary resume upload + primary CTA ── */}
        <section className="max-w-3xl w-full mx-auto px-4 pt-4 pb-10 border-t border-slate-50 mt-2">
          <div className="flex flex-col items-center gap-4">
            <div className="flex flex-wrap justify-center gap-3">
              <>
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
                <button
                  type="button"
                  disabled={isSubmitting || extractPdf.isPending}
                  onClick={() => fileInputRef.current?.click()}
                  className="upload-pill w-full max-w-xl py-3.5 px-8 text-[11px] font-bold uppercase tracking-[0.18em] text-center disabled:opacity-50"
                >
                  {extractPdf.isPending
                    ? 'Reading resume…'
                    : resumeFileName
                      ? `✓ ${resumeFileName}`
                      : 'Optional: Upload your Resume for personalization'}
                </button>
                {resumeError && (
                  <p className="text-xs text-red-500 mt-1">{resumeError}</p>
                )}
              </>
            </div>
            <Button
              size="lg"
              onClick={handleBeginLearning}
              loading={false}
              disabled={pageState === 'idle' || !learningGoal.trim()}
              className="w-full sm:w-auto rounded-full !bg-[#78B3BA] hover:!bg-[#6aa3aa] !text-white px-10 py-4 text-lg font-semibold shadow-xl shadow-teal-500/20"
            >
              Begin Journey
            </Button>
          </div>
        </section>
      </div>
    </div>
  );
}
