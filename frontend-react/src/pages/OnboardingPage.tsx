import { useState, useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, InputField } from '@/components/ui';
import { cn } from '@/lib/cn';
import { useHasEnteredGoal } from '@/context/HasEnteredGoalContext';
import { useActiveGoal } from '@/context/GoalsContext';
import { usePersonas } from '@/api/endpoints/config';

/* ------------------------------------------------------------------ */
/*  Mock data                                                         */
/* ------------------------------------------------------------------ */

interface Category {
  id: string;
  label: string;
}

const CATEGORIES: Category[] = [
  { id: 'language',  label: 'Learn a new language' },
  { id: 'practical', label: 'Build a practical skill' },
  { id: 'career',    label: 'Career related skill' },
  { id: 'design',    label: 'Design skill' },
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
    title: 'Hands-on Explorer',
    description: 'Learns best by doing. Prefers step-by-step practice and examples.',
    tags: ['Active', 'Visual', 'Step-by-step'],
  },
  {
    id: 'reflective',
    title: 'Reflective Reader',
    description: 'Learns through reading and reflection. Prefers detailed explanations.',
    tags: ['Reading', 'Reflection'],
  },
  {
    id: 'visual',
    title: 'Visual Learner',
    description: 'Prefers diagrams and videos. Likes seeing concepts shown clearly.',
    tags: ['Visual', 'Diagrams'],
  },
  {
    id: 'conceptual',
    title: 'Conceptual Thinker',
    description: 'Enjoys theories and the big picture. Likes analysis and connections.',
    tags: ['Theory', 'Analysis', 'Big-picture'],
  },
  {
    id: 'balanced',
    title: 'Balanced Learner',
    description: 'No strong preference. Adapts to different learning formats.',
    tags: ['Flexible', 'Neutral'],
  },
];

type OnboardingState = 'idle' | 'category-selected' | 'goal-refined' | 'preference' | 'submitting';

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function OnboardingPage() {
  const navigate = useNavigate();
  const { setHasEnteredGoal } = useHasEnteredGoal();
  const { activeGoal, selectedGoalId } = useActiveGoal();
  const { data: personasData } = usePersonas();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [learningGoal, setLearningGoal] = useState('');
  const [isRefining, setIsRefining] = useState(false);
  const [refinedText, setRefinedText] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPreferenceModule, setShowPreferenceModule] = useState(false);
  const [selectedPreferenceId, setSelectedPreferenceId] = useState<string | null>('hands-on');
  const [resumeText, setResumeText] = useState('');
  const personas = personasData?.personas ?? {};

  const pageState: OnboardingState = isSubmitting
    ? 'submitting'
    : showPreferenceModule
      ? 'preference'
      : refinedText !== null || learningGoal.trim()
        ? 'goal-refined'
        : selectedCategory !== null
          ? 'category-selected'
          : 'idle';

  const handleSelectCategory = useCallback(
    (id: string) => {
      const next = selectedCategory === id ? null : id;
      setSelectedCategory(next);
      setRefinedText(null);
      if (next) {
        const cat = CATEGORIES.find((c) => c.id === next);
        setLearningGoal(cat ? `${cat.label}: ` : '');
      } else {
        setLearningGoal('');
      }
    },
    [selectedCategory],
  );

  const handleRefine = useCallback(() => {
    if (!learningGoal.trim()) return;
    setIsRefining(true);
    setTimeout(() => {
      setRefinedText(
        `${learningGoal.trim()} — refined by AI with a personalized study plan.`,
      );
      setIsRefining(false);
    }, 1200);
  }, [learningGoal]);

  const handleBeginLearning = useCallback(() => {
    const trimmed = learningGoal.trim();
    if (!trimmed) return;
    const personaKey = selectedPreferenceId;
    // Build learnerInformation similar to old frontend: persona + optional resume summary
    let learnerInformation = resumeText;
    if (personaKey && personas[personaKey]) {
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

  const handleSkipPreference = useCallback(() => {
    setShowPreferenceModule(false);
  }, []);

  return (
    <div className="flex flex-col min-h-0 flex-1">
      {/* ── Scrollable content ── */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {/* ── Hero ── */}
        <section className="text-center pt-8 pb-6 px-4">
          <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">
            Welcome to <span className="text-primary-600">Ami</span>
          </h1>
          <p className="mt-3 text-lg text-slate-500 max-w-lg mx-auto leading-relaxed">
            Your personal adaptive learning companion.
            <br />
            No setup required — we&apos;ll adapt to you as we go.
          </p>
        </section>

        {/* ── Preference module (design: Select Your Learning Preference) ── */}
        {showPreferenceModule ? (
          <section className="max-w-4xl w-full mx-auto px-4 pb-8">
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 sm:p-8">
              <h2 className="text-lg font-semibold text-slate-900 mb-6">
                Select Your Learning Preference
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
                {LEARNING_PREFERENCES.map((pref) => {
                  const isSelected = selectedPreferenceId === pref.id;
                  return (
                    <button
                      key={pref.id}
                      type="button"
                      onClick={() => setSelectedPreferenceId(pref.id)}
                      disabled={isSubmitting}
                      className={cn(
                        'text-left rounded-lg border-2 p-4 transition-all',
                        'hover:border-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                        isSelected
                          ? 'border-slate-800 bg-slate-50'
                          : 'border-slate-200 bg-white',
                      )}
                    >
                      <span className="font-semibold text-slate-900 text-sm block mb-2">{pref.title}</span>
                      <p className="text-xs text-slate-600 leading-relaxed mb-3">{pref.description}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {pref.tags.map((tag, i) => (
                          <span
                            key={tag}
                            className={cn(
                              'text-xs px-2 py-0.5 rounded-full',
                              isSelected && i === 0
                                ? 'bg-slate-700 text-white'
                                : 'bg-slate-100 text-slate-600',
                            )}
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </button>
                  );
                })}
              </div>
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleSkipPreference}
                  disabled={isSubmitting}
                  className="border-slate-300"
                >
                  Skip
                </Button>
                <Button
                  type="button"
                  onClick={handleBeginLearning}
                  loading={false}
                  className="!bg-slate-800 hover:!bg-slate-700 !text-white"
                >
                  Begin Learning
                </Button>
              </div>
            </div>

            {/* Optional: Resume & LinkedIn (with info icon) */}
            <div className="mt-6 space-y-3">
              <button
                type="button"
                disabled={isSubmitting}
                className="w-full flex items-center gap-3 text-left px-4 py-3 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-50 transition-colors"
              >
                <span className="w-5 h-5 rounded-full border border-slate-400 flex items-center justify-center text-slate-600 text-xs font-bold shrink-0">
                  i
                </span>
                <span className="text-sm font-medium text-slate-700">Upload Your Resume (Optional)</span>
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                className="w-full flex items-center gap-3 text-left px-4 py-3 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-50 transition-colors"
              >
                <span className="w-5 h-5 rounded-full border border-slate-400 flex items-center justify-center text-slate-600 text-xs font-bold shrink-0">
                  i
                </span>
                <span className="text-sm font-medium text-slate-700">Connect to your LinkedIn</span>
              </button>
            </div>
          </section>
        ) : (
        /* ── Main content (goal + categories) ── */
        <section className="max-w-2xl w-full mx-auto px-4 space-y-6 pb-8">
          {/* Question prompt */}
          <p className="text-center text-sm font-medium text-slate-700">
            What would you like to learn today?
          </p>

          {/* Input + AI refine */}
          <div className="flex items-start gap-3">
            <div className="flex-1">
              <InputField
                placeholder="eg: learn english, python, data ..."
                value={learningGoal}
                onChange={(e) => {
                  setLearningGoal(e.target.value);
                  setRefinedText(null);
                }}
                disabled={isSubmitting}
              />
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleRefine}
              loading={false}
              disabled={!learningGoal.trim() || isSubmitting || isRefining}
              className="mt-0.5 whitespace-nowrap"
            >
              AI Refinement
            </Button>
          </div>

          {/* Refined result badge */}
          {refinedText && (
            <div className="bg-primary-50 border border-primary-200 rounded-lg px-4 py-3 text-sm text-primary-800">
              <span className="font-medium">Refined goal:</span> {refinedText}
            </div>
          )}

          {/* Category cards */}
          <div className="grid grid-cols-2 gap-3">
            {CATEGORIES.map((cat) => {
              const isSelected = selectedCategory === cat.id;
              return (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => handleSelectCategory(cat.id)}
                  disabled={isSubmitting}
                  className={cn(
                    'relative text-left px-4 py-3.5 rounded-lg border-2 transition-all text-sm font-medium',
                    'hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                    isSelected
                      ? 'border-primary-500 bg-primary-50 text-primary-800'
                      : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300',
                  )}
                >
                  {cat.label}
                </button>
              );
            })}
          </div>

          {/* Hint + Adjust preference */}
          <div className="flex items-start justify-between gap-4">
            <p className="text-xs text-slate-500 leading-relaxed">
              <span className="text-amber-500 mr-1">💡</span>
              Enter any topic you want to learn, and the system will automatically
              generate personalized content for you.
            </p>
            <Button variant="secondary" size="sm" disabled={isSubmitting} onClick={() => setShowPreferenceModule(true)}>
              Adjust Preference
            </Button>
          </div>
        </section>
        )}

        {/* ── Bottom action bar：Begin Learning 居中，其余两按钮在下方 ── */}
        <section className="max-w-2xl w-full mx-auto px-4 pt-4 pb-8 border-t border-slate-100 mt-3">
          <div className="flex flex-col items-center gap-4">
            <Button
              size="lg"
              onClick={handleBeginLearning}
              loading={false}
              disabled={pageState === 'idle' || !learningGoal.trim()}
              className="w-full sm:w-auto !bg-primary-600 hover:!bg-primary-700 !text-white px-10"
            >
              Begin Learning
            </Button>
            <div className="flex flex-wrap justify-center gap-3">
              <>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    // Minimal placeholder: store filename into resumeText so it is visible to backend;
                    // if you later wire extract-pdf-text, replace this with real text.
                    setResumeText(`Resume file uploaded: ${file.name}`);
                  }}
                />
                <Button
                  variant="secondary"
                  size="md"
                  disabled={isSubmitting}
                  onClick={() => fileInputRef.current?.click()}
                >
                  Upload Your Resume (Optional)
                </Button>
              </>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
