import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Modal } from '@/components/ui';
import { cn } from '@/lib/cn';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/context/GoalsContext';
import { useDeleteUserData, useUpdateLearnerInformation, useUpdateLearningPreferences } from '@/api/endpoints/content';
import { useBehavioralMetrics } from '@/api/endpoints/metrics';
import { useDeleteUser, useAuthMe } from '@/api/endpoints/auth';
import { useAppConfig, usePersonas } from '@/api/endpoints/config';
import { useExtractPdfText } from '@/api/endpoints/pdf';
import {
  getLearningStylePreference,
  setLearningStylePreference,
  type LearningStyleOption,
} from '@/lib/learningStylePreference';
import {
  getMemberSinceIso,
  formatMemberSinceDisplay,
  earliestGoalTimestampIso,
} from '@/lib/memberSince';
import {
  getAvatarDataUrl,
  setAvatarFromFile,
  clearAvatar,
} from '@/lib/avatarStorage';
import {
  getStoredResumeFileName,
  setStoredResume,
  clearStoredResume,
} from '@/lib/resumeStorage';

function formatDuration(secs: number): string {
  if (secs <= 0 || !Number.isFinite(secs)) return '—';
  if (secs < 60) return `${Math.round(secs)}s`;
  if (secs < 3600) return `${Math.round(secs / 60)}m`;
  const h = Math.floor(secs / 3600);
  const m = Math.round((secs % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

/* ── Persona definitions (aligned with OnboardingPage) ────────────── */

interface PersonaOption {
  id: string;
  personaKey: string;
  title: string;
  learningStyle: LearningStyleOption;
  description: string;
  tags: string[];
}

const PERSONA_OPTIONS: PersonaOption[] = [
  {
    id: 'hands-on',
    personaKey: 'Hands-on Explorer',
    title: 'Interactive',
    learningStyle: 'Interactive',
    description: 'Learns best by doing and practicing with examples.',
    tags: ['Active', 'Visual', 'Step-by-step'],
  },
  {
    id: 'reflective',
    personaKey: 'Reflective Reader',
    title: 'Textual',
    learningStyle: 'Textual',
    description: 'Learns through reading and reflection. Prefers detailed explanations.',
    tags: ['Reading', 'Reflection'],
  },
  {
    id: 'visual',
    personaKey: 'Visual Learner',
    title: 'Visual',
    learningStyle: 'Visual',
    description: 'Understands concepts best through visuals and diagrams.',
    tags: ['Visual', 'Diagrams'],
  },
  {
    id: 'conceptual',
    personaKey: 'Conceptual Thinker',
    title: 'Concise',
    learningStyle: 'Concise',
    description: 'Enjoys big-picture ideas, theory, and analysis.',
    tags: ['Theory', 'Analysis', 'Big-picture'],
  },
  {
    id: 'balanced',
    personaKey: 'Balanced Learner',
    title: 'Balanced',
    learningStyle: 'Balanced',
    description: 'Flexible across different learning formats.',
    tags: ['Flexible', 'Neutral'],
  },
];

/* ── FSLSM-based learning preference helpers ─────────────────────── */

const FSLSM_THRESHOLD = 0.3;
const FSLSM_STRONG = 0.7;

interface PreferenceCardData {
  type: string;
  title: string;
  description: string;
}

function deriveFslsmPreferenceCards(
  dims: Record<string, number> | undefined,
): PreferenceCardData[] {
  if (!dims) return [];
  const cards: PreferenceCardData[] = [];

  const input = dims.fslsm_input ?? 0;
  if (input <= -FSLSM_THRESHOLD)
    cards.push({ type: 'visual', title: 'Visual materials', description: 'I prefer diagrams, charts, and videos over text.' });
  else if (input >= FSLSM_THRESHOLD)
    cards.push({ type: 'text', title: 'Text-based content', description: 'I prefer written explanations and detailed narratives.' });

  const perception = dims.fslsm_perception ?? 0;
  if (perception <= -FSLSM_THRESHOLD)
    cards.push({ type: 'practical', title: 'Practical examples', description: 'I prefer seeing real-world uses before theory.' });
  else if (perception >= FSLSM_THRESHOLD)
    cards.push({ type: 'conceptual', title: 'Conceptual thinking', description: 'I prefer understanding theory and concepts first.' });

  const understanding = dims.fslsm_understanding ?? 0;
  if (understanding <= -FSLSM_THRESHOLD)
    cards.push({ type: 'sequential', title: 'Step-by-step', description: 'I prefer clear, guided, linear progression.' });
  else if (understanding >= FSLSM_THRESHOLD)
    cards.push({ type: 'global', title: 'Big-picture first', description: 'I prefer seeing the overview before diving into details.' });

  const processing = dims.fslsm_processing ?? 0;
  if (processing <= -FSLSM_THRESHOLD)
    cards.push({ type: 'interactive', title: 'Interactive exercises', description: 'I prefer quizzes, sandboxes, and hands-on tasks.' });
  else if (processing >= FSLSM_THRESHOLD)
    cards.push({ type: 'reflective', title: 'Reflective learning', description: 'I prefer reading, observation, and time to reflect.' });

  return cards;
}

function deriveFslsmBullets(dims: Record<string, number> | undefined): string[] {
  if (!dims) return [];
  const bullets: string[] = [];

  const input = dims.fslsm_input ?? 0;
  if (input <= -FSLSM_STRONG) bullets.push('Prioritizes visual content and infographics.');
  else if (input <= -FSLSM_THRESHOLD) bullets.push('Includes visual aids like diagrams and charts.');
  else if (input >= FSLSM_STRONG) bullets.push('Focuses on detailed written and narrated explanations.');
  else if (input >= FSLSM_THRESHOLD) bullets.push('Enriches content with written and narrative-style material.');

  const perception = dims.fslsm_perception ?? 0;
  if (perception <= -FSLSM_STRONG) bullets.push('Introduces concepts through concrete examples first.');
  else if (perception <= -FSLSM_THRESHOLD) bullets.push('Leads with practical examples before theoretical concepts.');
  else if (perception >= FSLSM_STRONG) bullets.push('Presents theoretical frameworks and concepts upfront.');
  else if (perception >= FSLSM_THRESHOLD) bullets.push('Emphasizes conceptual understanding before examples.');

  const understanding = dims.fslsm_understanding ?? 0;
  if (understanding <= -FSLSM_STRONG) bullets.push('Structures lessons in strict, bite-sized sequences.');
  else if (understanding <= -FSLSM_THRESHOLD) bullets.push('Organizes content in a structured, sequential order.');
  else if (understanding >= FSLSM_STRONG) bullets.push('Starts with big-picture overviews before diving into details.');
  else if (understanding >= FSLSM_THRESHOLD) bullets.push('Provides big-picture framing before sequential detail.');

  const processing = dims.fslsm_processing ?? 0;
  if (processing <= -FSLSM_STRONG) bullets.push('Integrates frequent interactive knowledge checks.');
  else if (processing <= -FSLSM_THRESHOLD) bullets.push('Includes hands-on activities and practice opportunities.');
  else if (processing >= FSLSM_STRONG) bullets.push('Allows ample time for reflection and deep thinking.');
  else if (processing >= FSLSM_THRESHOLD) bullets.push('Provides reflection time before moving to new topics.');

  if (bullets.length === 0) bullets.push('Delivers a balanced mix of content styles and activities.');
  return bullets;
}

function PreferenceIcon({ type }: { type: string }) {
  const cls = 'w-5 h-5';
  switch (type) {
    case 'visual':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z" />
        </svg>
      );
    case 'text':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
        </svg>
      );
    case 'practical':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75a4.5 4.5 0 0 1-4.884 4.484c-1.076-.091-2.264.071-2.95.904l-7.152 8.684a2.548 2.548 0 1 1-3.586-3.586l8.684-7.152c.833-.686.995-1.874.904-2.95a4.5 4.5 0 0 1 6.336-4.486l-3.276 3.276a3.004 3.004 0 0 0 2.25 2.25l3.276-3.276c.256.565.398 1.192.398 1.852Z" />
        </svg>
      );
    case 'conceptual':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 0 0 1.5-.189m-1.5.189a6.01 6.01 0 0 1-1.5-.189m3.75 7.478a12.06 12.06 0 0 1-4.5 0m3.75 2.383a14.406 14.406 0 0 1-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 1 0-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
        </svg>
      );
    case 'sequential':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 0 1 0 3.75H5.625a1.875 1.875 0 0 1 0-3.75Z" />
        </svg>
      );
    case 'global':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5a17.92 17.92 0 0 1-8.716-2.247m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418" />
        </svg>
      );
    case 'interactive':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.456-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.456-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.456 2.456Z" />
        </svg>
      );
    case 'reflective':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
        </svg>
      );
    default:
      return null;
  }
}

export function ProfilePage() {
  const navigate = useNavigate();
  const { userId, logout } = useAuthContext();
  const { goals, refreshGoals, updateGoal } = useGoalsContext();
  const { activeGoal } = useActiveGoal();
  const { data: config } = useAppConfig();

  const { data: authMe } = useAuthMe(Boolean(userId));
  const { data: metrics, isLoading: metricsLoading } = useBehavioralMetrics(
    userId ?? undefined,
    activeGoal?.id,
  );
  const { data: personasData } = usePersonas();
  const deleteUserDataMutation = useDeleteUserData();
  const deleteUserMutation = useDeleteUser();
  const updateLearnerInfoMutation = useUpdateLearnerInformation();
  const updatePreferencesMutation = useUpdateLearningPreferences();
  const extractPdf = useExtractPdfText();

  const [learningStyle, setLearningStyle] = useState(() => getLearningStylePreference());
  useEffect(() => {
    setLearningStyle(getLearningStylePreference());
  }, [activeGoal?.id]);
  const [showPreferencesModal, setShowPreferencesModal] = useState(false);
  const [selectedPersonaId, setSelectedPersonaId] = useState<string | null>(null);
  const [preferencesSaveError, setPreferencesSaveError] = useState<string | null>(null);
  const [showDeleteDataConfirm, setShowDeleteDataConfirm] = useState(false);
  const [showDeleteAccountConfirm, setShowDeleteAccountConfirm] = useState(false);
  const [resumeName, setResumeName] = useState<string | null>(() => getStoredResumeFileName());
  const [resumeStatus, setResumeStatus] = useState<string | null>(null);
  const [avatarDataUrl, setAvatarDataUrl] = useState<string | null>(null);
  const [avatarMessage, setAvatarMessage] = useState<string | null>(null);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setAvatarDataUrl(getAvatarDataUrl(userId));
    setAvatarMessage(null);
  }, [userId]);

  const profileTags: string[] = [];
  if (activeGoal?.learner_profile?.goal_display_name) {
    profileTags.push('Active learner');
  }
  if (learningStyle) {
    profileTags.push(learningStyle);
  }
  if (profileTags.length === 0) profileTags.push('Learner');

  // Member since: prefer auth/me created_at, then first-login localStorage, then earliest goal timestamp
  const memberSinceIso =
    (authMe as { created_at?: string } | undefined)?.created_at ||
    getMemberSinceIso(userId) ||
    earliestGoalTimestampIso(goals as unknown as Array<Record<string, unknown>>);
  const memberSinceDisplay = formatMemberSinceDisplay(memberSinceIso);

  const handleRestartOnboarding = async () => {
    if (!userId) return;
    try {
      await deleteUserDataMutation.mutateAsync(userId);
      refreshGoals();
      navigate('/onboarding');
    } catch {
      // ignore
    } finally {
      setShowDeleteDataConfirm(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (!userId) return;
    try {
      await deleteUserMutation.mutateAsync();
      logout();
      navigate('/login');
    } catch {
      // ignore
    } finally {
      setShowDeleteAccountConfirm(false);
    }
  };

  const handleOpenPreferencesModal = () => {
    setPreferencesSaveError(null);
    const currentPersona = PERSONA_OPTIONS.find((p) => {
      const dims = personasData?.personas?.[p.personaKey]?.fslsm_dimensions;
      if (!dims || !fslsmDims) return false;
      return Object.keys(dims).every(
        (k) => Math.abs((dims[k] ?? 0) - (fslsmDims[k] ?? 0)) < 0.15,
      );
    });
    setSelectedPersonaId(currentPersona?.id ?? null);
    setShowPreferencesModal(true);
  };

  const handleSavePreferences = async () => {
    const persona = PERSONA_OPTIONS.find((p) => p.id === selectedPersonaId);
    if (!persona || !activeGoal || !userId) return;
    const personaDims = personasData?.personas?.[persona.personaKey]?.fslsm_dimensions;
    if (!personaDims) return;

    setPreferencesSaveError(null);
    const currentProfile = activeGoal.learner_profile ?? {};
    const sliderPayload = {
      update_mode: 'fslsm_slider_override',
      slider_values: personaDims,
    };

    try {
      const res = await updatePreferencesMutation.mutateAsync({
        learner_profile: JSON.stringify(currentProfile),
        learner_interactions: JSON.stringify(sliderPayload),
        user_id: userId,
        goal_id: activeGoal.id,
      });
      updateGoal(activeGoal.id, { ...activeGoal, learner_profile: res.learner_profile });
      setLearningStylePreference(persona.learningStyle);
      setLearningStyle(persona.learningStyle);
      setShowPreferencesModal(false);
    } catch {
      setPreferencesSaveError('Failed to update preferences. Please try again.');
    }
  };

  const behavioralMetrics: any = metrics ?? {};
  const masteryHistory: number[] = behavioralMetrics.mastery_history ?? [];
  void behavioralMetrics.sessions_completed;
  void behavioralMetrics.total_sessions_in_path;
  void behavioralMetrics.total_learning_time_sec;
  void behavioralMetrics.latest_mastery_rate;
  void behavioralMetrics.motivational_triggers_count;

  let streakDays = 0;
  for (let i = masteryHistory.length - 1; i >= 0; i -= 1) {
    if (masteryHistory[i] > 0) streakDays += 1;
    else break;
  }

  const masteryThreshold =
    (config?.mastery_threshold_default as number | undefined) ?? 0.6;
  void masteryHistory.filter((v) => v >= masteryThreshold).length;
  void masteryHistory.length;

  const biasInfo = activeGoal?.profile_fairness as Record<string, unknown> | undefined;

  const learnerInformation = (
    activeGoal?.learner_profile as { learner_information?: string } | undefined
  )?.learner_information;

  const fslsmDims = activeGoal?.learner_profile?.learning_preferences?.fslsm_dimensions;
  const preferenceCards = deriveFslsmPreferenceCards(fslsmDims);
  const personalizationBullets = deriveFslsmBullets(fslsmDims);

  const handleResumeUpload: React.ChangeEventHandler<HTMLInputElement> = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !userId || !activeGoal) return;
    setResumeStatus(null);
    setResumeName(file.name);
    try {
      const result = await extractPdf.mutateAsync(file);
      const pdfText = (result as { text?: string }).text ?? '';
      if (!pdfText) {
        setResumeStatus('Failed to read PDF. Please try another file.');
        return;
      }
      const currentProfile = (activeGoal.learner_profile ?? {}) as Record<string, unknown>;
      const res = await updateLearnerInfoMutation.mutateAsync({
        learner_profile: JSON.stringify(currentProfile),
        updated_learner_information:
          (currentProfile.learner_information as string | undefined) ?? '',
        resume_text: pdfText,
        user_id: userId,
        goal_id: activeGoal.id,
      });
      updateGoal(activeGoal.id, { ...activeGoal, learner_profile: res.learner_profile });
      setStoredResume(file.name, `Resume summary: ${pdfText}`);
      setResumeStatus('Resume connected successfully.');
    } catch {
      setResumeStatus('Upload failed. Please try again.');
    } finally {
      e.target.value = '';
    }
  };

  const handleResumeRemove = async () => {
    if (!userId || !activeGoal) {
      setResumeName(null);
      setResumeStatus(null);
      return;
    }
    try {
      setResumeStatus(null);
      const currentProfile = (activeGoal.learner_profile ?? {}) as Record<string, unknown>;
      const res = await updateLearnerInfoMutation.mutateAsync({
        learner_profile: JSON.stringify(currentProfile),
        updated_learner_information:
          (currentProfile.learner_information as string | undefined) ?? '',
        resume_text: '',
        user_id: userId,
        goal_id: activeGoal.id,
      });
      updateGoal(activeGoal.id, { ...activeGoal, learner_profile: res.learner_profile });
      setResumeName(null);
      clearStoredResume();
      setResumeStatus('Resume removed from profile.');
    } catch {
      setResumeStatus('Failed to remove resume. Please try again.');
    }
  };

  return (
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6">
      {/* Top profile card */}
      <section className="bg-white rounded-xl border border-slate-200 p-6 flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex flex-col items-center gap-1 shrink-0">
          {userId && (
            <input
              ref={avatarInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                e.target.value = '';
                if (!file || !userId) return;
                setAvatarMessage(null);
                const result = await setAvatarFromFile(userId, file);
                if (result.ok) {
                  setAvatarDataUrl(getAvatarDataUrl(userId));
                  setAvatarMessage('Saved on this device.');
                } else {
                  setAvatarMessage(result.error);
                }
              }}
            />
          )}
          <div className="relative w-20 h-20 rounded-full bg-slate-200 shrink-0 overflow-hidden ring-2 ring-slate-100 group">
            {avatarDataUrl ? (
              <img
                src={avatarDataUrl}
                alt=""
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <svg className="w-10 h-10 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
                </svg>
              </div>
            )}
            {userId && (
              <>
                <button
                  type="button"
                  aria-label="Change profile photo"
                  className="absolute left-1/2 top-1/2 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-black/45 text-white shadow-md transition-colors hover:bg-black/55 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1"
                  onClick={() => avatarInputRef.current?.click()}
                >
                  {/* Camera icon — click opens file picker */}
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
                    />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </button>
                {avatarDataUrl && (
                  <button
                    type="button"
                    aria-label="Remove profile photo"
                    className="absolute top-0.5 right-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/50 text-white text-xs hover:bg-black/70"
                    onClick={(e) => {
                      e.stopPropagation();
                      clearAvatar(userId);
                      setAvatarDataUrl(null);
                      setAvatarMessage('Removed.');
                    }}
                  >
                    ×
                  </button>
                )}
              </>
            )}
          </div>
          {avatarMessage && (
            <p className="text-[10px] text-slate-500 text-center max-w-[140px]">{avatarMessage}</p>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-semibold text-slate-900">
            {userId ?? 'Learner'}
          </h2>
          <p className="mt-0.5 text-sm text-slate-500">@{userId ?? 'guest'}</p>
          <div className="flex flex-wrap gap-2 mt-2">
            {profileTags.map((tag) => (
              <span
                key={tag}
                className="text-xs font-medium px-2.5 py-1 rounded-full bg-slate-100 text-slate-600"
              >
                {tag}
              </span>
            ))}
          </div>
          {learnerInformation && (
            <p className="mt-2 text-xs text-slate-500 whitespace-pre-line">
              {learnerInformation}
            </p>
          )}
        </div>
        <div className="flex items-center gap-4 shrink-0">
          {/* Edit profile placeholder· */}
          {/* <button
            type="button"
            className="text-sm font-medium text-slate-700 hover:text-slate-900 transition-colors"
            disabled
          >
            Edit Profile
          </button> */}
          <button
            type="button"
            className="text-sm font-medium text-slate-700 hover:text-slate-900 transition-colors"
            onClick={() => {
              logout();
              navigate('/login');
            }}
          >
            Sign out
          </button>
        </div>
      </section>

      {/* Bias / fairness info banner (if available) */}
      {biasInfo && (
        <section className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-900">
          <p className="font-medium">Bias & fairness notice</p>
          <p className="mt-1 text-xs text-amber-800">
            Your current learning profile has been evaluated for potential bias. Review analytics
            and skill gaps to ensure your goals are inclusive and fair.
          </p>
        </section>
      )}

      {/* Grid: Account | Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ACCOUNT */}
        <section className="bg-white rounded-xl border border-slate-200 p-5">
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Account</h3>
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-slate-500 font-medium">Email</dt>
              <dd className="text-slate-900 mt-0.5">
                {userId ? `${userId}@example` : 'Not connected'}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500 font-medium">Member since</dt>
              <dd className="text-slate-900 mt-0.5">
                {memberSinceDisplay}
                {memberSinceIso == null && userId && (
                  <span className="block text-xs text-slate-400 mt-0.5">
                    Shown after first sign-in on this device, or when the API returns account creation time.
                  </span>
                )}
              </dd>
            </div>
            {/* <div>
              <dt className="text-slate-500 font-medium">Plan</dt>
              <dd className="mt-0.5 flex items-center gap-2">
                <span className="text-slate-900">Free</span>
                <button
                  type="button"
                  className="text-slate-600 hover:text-slate-900 font-medium text-xs"
                  disabled
                >
                  Upgrade →
                </button>
              </dd>
            </div> */}
          </dl>
        </section>

        {/* ACTIVITY SUMMARY */}
        <section className="bg-white rounded-xl border border-slate-200 p-5">
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Activity Summary</h3>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-slate-500">Goals created</dt>
              <dd className="text-slate-900 font-medium">{goals.length}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Sessions completed</dt>
              <dd className="text-slate-900 font-medium">
                {metricsLoading || !metrics
                  ? '—'
                  : `${metrics.sessions_completed} / ${metrics.total_sessions_in_path}`}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Total study time</dt>
              <dd className="text-slate-900 font-bold">
                {metricsLoading || !metrics ? '—' : formatDuration(metrics.total_learning_time_sec)}
              </dd>
            </div>
            <div className="flex justify-between items-center">
              <dt className="text-slate-500">Latest mastery rate</dt>
              <dd className="text-slate-900 font-bold">
                {metricsLoading || !metrics || metrics.latest_mastery_rate == null
                  ? '—'
                  : `${Math.round(metrics.latest_mastery_rate * 100)}%`}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Motivational triggers</dt>
              <dd className="text-slate-900 font-medium">
                {metricsLoading || !metrics ? '—' : metrics.motivational_triggers_count}
              </dd>
            </div>
          </dl>
        </section>

      </div>

      {/* LEARNING PREFERENCES */}
      <section className="bg-white rounded-xl border border-slate-200 p-6">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.456-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.456-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.456 2.456Z" />
            </svg>
            <h3 className="text-lg font-semibold text-slate-900">How You Learn</h3>
          </div>
          <Button
            size="sm"
            onClick={handleOpenPreferencesModal}
          >
            Edit Preferences
          </Button>
        </div>
        <p className="text-sm text-slate-500 flex items-center gap-1.5 mb-6">
          <svg className="w-4 h-4 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z" />
          </svg>
          Current preference: {learningStyle ?? 'Balanced'}. Applied by default to new learning goals.
        </p>

        {preferenceCards.length > 0 ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left: preference cards */}
            <div>
              <div className="space-y-3">
                {preferenceCards.map((card) => (
                  <div
                    key={card.type}
                    className="flex items-center gap-3 rounded-lg border border-slate-200 px-4 py-3"
                  >
                    <div className="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center shrink-0 text-slate-600">
                      <PreferenceIcon type={card.type} />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{card.title}</p>
                      <p className="text-xs text-slate-500">{card.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Right: HOW AMI PERSONALIZES */}
            <div className="rounded-xl bg-teal-50/60 border border-teal-100 p-5">
              <div className="flex items-center gap-2 mb-4">
                <svg className="w-4 h-4 text-teal-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.456-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.456-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.456 2.456Z" />
                </svg>
                <p className="text-xs font-semibold text-teal-800 uppercase tracking-wider">
                  How Ami personalizes your content
                </p>
              </div>
              <ul className="space-y-2.5">
                {personalizationBullets.map((bullet, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm text-teal-900">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-teal-500 shrink-0" />
                    {bullet}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : (
          <div className="text-center py-8 text-slate-400">
            <p className="text-sm">No learning preferences available yet.</p>
            <p className="text-xs mt-1">Complete onboarding to set your preferences.</p>
          </div>
        )}
      </section>

      {/* TALENT ASSETS */}
      <section className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Talent Assets</h3>
        <div className="border border-slate-200 rounded-lg p-4 bg-slate-50 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-slate-200 flex items-center justify-center shrink-0">
              <svg className="w-6 h-6 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-900 truncate">
                {resumeName ?? 'No resume connected'}
              </p>
              <p className="text-xs text-slate-500 mt-0.5">
                Upload a PDF resume to enrich your learner profile. Ami uses only the extracted text.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {resumeName ? (
              <>
                <label className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium rounded-md bg-primary-600 text-white hover:bg-primary-700 cursor-pointer">
                  <input
                    type="file"
                    accept=".pdf"
                    className="hidden"
                    onChange={handleResumeUpload}
                  />
                  {extractPdf.isPending || updateLearnerInfoMutation.isPending ? 'Uploading…' : 'Update'}
                </label>
                <button
                  type="button"
                  onClick={handleResumeRemove}
                  className="px-3 py-1.5 text-sm font-medium rounded-md border border-slate-300 text-slate-700 hover:bg-slate-100"
                >
                  Remove
                </button>
              </>
            ) : (
              <label className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium rounded-md bg-primary-600 text-white hover:bg-primary-700 cursor-pointer">
                <input
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={handleResumeUpload}
                />
                {extractPdf.isPending || updateLearnerInfoMutation.isPending ? 'Uploading…' : 'Upload PDF'}
              </label>
            )}
          </div>
        </div>
        {resumeStatus && (
          <p className="text-xs text-slate-600">
            {resumeStatus}
          </p>
        )}
      </section>

      {/* Data & account actions */}
      <section className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Data & Account</h3>
        {!showDeleteDataConfirm ? (
          <button
            type="button"
            onClick={() => setShowDeleteDataConfirm(true)}
            className="text-sm text-slate-600 hover:text-slate-800 underline"
          >
            Restart onboarding (clear all data)
          </button>
        ) : (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-2">
            <p className="text-sm text-amber-800">
              This will delete all your goals, learning history, and profile data. Are you sure?
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={handleRestartOnboarding}
                loading={deleteUserDataMutation.isPending}
                className="!bg-amber-600 hover:!bg-amber-700 !text-white"
              >
                Yes, restart
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setShowDeleteDataConfirm(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {!showDeleteAccountConfirm ? (
          <button
            type="button"
            onClick={() => setShowDeleteAccountConfirm(true)}
            className="text-sm text-red-500 hover:text-red-700 underline"
          >
            Delete account
          </button>
        ) : (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 space-y-2">
            <p className="text-sm text-red-800">
              This will permanently delete your account and all data. This cannot be undone.
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={handleDeleteAccount}
                loading={deleteUserMutation?.isPending}
                className="!bg-red-600 hover:!bg-red-700 !text-white"
              >
                Delete account
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setShowDeleteAccountConfirm(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </section>

      {/* ── Edit Preferences Modal ── */}
      <Modal
        open={showPreferencesModal}
        onClose={() => setShowPreferencesModal(false)}
        title="Edit Learning Preferences"
        maxWidth="max-w-2xl"
      >
        <p className="text-sm text-slate-500 mb-5">Choose the learning style that fits you best.</p>

        <div className="space-y-2">
          {PERSONA_OPTIONS.map((persona) => {
            const isSelected = selectedPersonaId === persona.id;
            return (
              <button
                key={persona.id}
                type="button"
                onClick={() => setSelectedPersonaId(persona.id)}
                className={cn(
                  'w-full text-left rounded-lg border-2 px-4 py-3 transition-all',
                  isSelected
                    ? 'border-primary-500 bg-primary-50/50 ring-1 ring-primary-200'
                    : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50',
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <p
                    className={cn(
                      'text-sm font-semibold',
                      isSelected ? 'text-primary-700' : 'text-slate-900',
                    )}
                  >
                    {persona.title}
                  </p>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">{persona.description}</p>
              </button>
            );
          })}
        </div>

        {preferencesSaveError && (
          <p className="text-sm text-red-600 mt-3">{preferencesSaveError}</p>
        )}

        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-slate-100">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setShowPreferencesModal(false)}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleSavePreferences}
            disabled={!selectedPersonaId || !activeGoal}
            loading={updatePreferencesMutation.isPending}
          >
            Save
          </Button>
        </div>
      </Modal>
    </div>
  );
}
