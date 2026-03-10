import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Toggle } from '@/components/ui';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/context/GoalsContext';
import { useDeleteUserData, useUpdateLearnerInformation } from '@/api/endpoints/content';
import { useBehavioralMetrics } from '@/api/endpoints/metrics';
import { useDeleteUser } from '@/api/endpoints/auth';
import { useAppConfig } from '@/api/endpoints/config';
import { useExtractPdfText } from '@/api/endpoints/pdf';

function formatDuration(secs: number): string {
  if (secs <= 0 || !Number.isFinite(secs)) return '—';
  if (secs < 60) return `${Math.round(secs)}s`;
  if (secs < 3600) return `${Math.round(secs / 60)}m`;
  const h = Math.floor(secs / 3600);
  const m = Math.round((secs % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

export function ProfilePage() {
  const navigate = useNavigate();
  const { userId, logout } = useAuthContext();
  const { goals, refreshGoals, updateGoal } = useGoalsContext();
  const { activeGoal } = useActiveGoal();
  const { data: config } = useAppConfig();

  const { data: metrics, isLoading: metricsLoading } = useBehavioralMetrics(
    userId ?? undefined,
    activeGoal?.id,
  );
  const deleteUserDataMutation = useDeleteUserData();
  const deleteUserMutation = useDeleteUser();
  const updateLearnerInfoMutation = useUpdateLearnerInformation();
  const extractPdf = useExtractPdfText();

  const [learningStyle, setLearningStyle] = useState('Balanced');
  const [aiDifficulty, setAiDifficulty] = useState(true);
  const [bilingualContent, setBilingualContent] = useState(false);
  const [showDeleteDataConfirm, setShowDeleteDataConfirm] = useState(false);
  const [showDeleteAccountConfirm, setShowDeleteAccountConfirm] = useState(false);
  const [resumeName, setResumeName] = useState<string | null>(null);
  const [resumeStatus, setResumeStatus] = useState<string | null>(null);

  const profileTags: string[] = [];
  if (activeGoal?.learner_profile?.goal_display_name) {
    profileTags.push('Active learner');
  }
  if (learningStyle) {
    profileTags.push(learningStyle);
  }
  if (profileTags.length === 0) profileTags.push('Learner');

  const fslsmDims =
    (activeGoal?.learner_profile?.learning_preferences
      ?.fslsm_dimensions as Record<string, number> | undefined) ?? {};

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

  const behavioralMetrics: any = metrics ?? {};
  const masteryHistory: number[] = behavioralMetrics.mastery_history ?? [];
  const sessionsCompletedMetric: number | undefined = behavioralMetrics.sessions_completed;
  const totalSessionsMetric: number | undefined = behavioralMetrics.total_sessions_in_path;
  const totalStudyTimeSec: number | undefined = behavioralMetrics.total_learning_time_sec;
  const latestMasteryRate: number | undefined = behavioralMetrics.latest_mastery_rate;
  const motivationalTriggers: number | undefined =
    behavioralMetrics.motivational_triggers_count;

  let streakDays = 0;
  for (let i = masteryHistory.length - 1; i >= 0; i -= 1) {
    if (masteryHistory[i] > 0) streakDays += 1;
    else break;
  }

  const masteryThreshold =
    (config?.mastery_threshold_default as number | undefined) ?? 0.6;
  const quizzesPassed = masteryHistory.filter((v) => v >= masteryThreshold).length;
  const quizzesTotal = masteryHistory.length;

  const biasInfo = activeGoal?.profile_fairness as Record<string, unknown> | undefined;

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
      setResumeStatus('Resume removed from profile.');
    } catch {
      setResumeStatus('Failed to remove resume. Please try again.');
    }
  };

  return (
    <div className="max-w-4xl space-y-6">
      {/* Top profile card */}
      <section className="bg-white rounded-xl border border-slate-200 p-6 flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="w-20 h-20 rounded-full bg-slate-200 shrink-0 flex items-center justify-center overflow-hidden">
          <svg className="w-10 h-10 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
          </svg>
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
        </div>
        <div className="flex items-center gap-4 shrink-0">
          {/* Edit profile 可后续接入真实编辑，这里暂留占位 */}
          <button
            type="button"
            className="text-sm font-medium text-slate-700 hover:text-slate-900 transition-colors"
            disabled
          >
            Edit Profile
          </button>
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
              <dd className="text-slate-900 mt-0.5">Not tracked yet</dd>
            </div>
            <div>
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
            </div>
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
      <section className="bg-white rounded-xl border border-slate-200 p-5">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">
          Learning Preferences
        </h3>
        <div className="space-y-5">
          {/* Presentation style */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-500 tracking-wide uppercase">
              Learning style
            </p>
            <div className="inline-flex w-full rounded-2xl bg-slate-100 p-1 border border-slate-200">
              {['Visual Learner', 'Balanced', 'Text-first'].map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setLearningStyle(option)}
                  className={`flex-1 px-4 py-2 text-sm font-medium rounded-2xl transition-all ${
                    learningStyle === option
                      ? 'bg-white shadow text-slate-900'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Used by Ami to decide how content is presented.
            </p>
          </div>

          {/* Content settings */}
          <div className="space-y-3 pt-2 border-t border-slate-100">
            <p className="text-xs font-semibold text-slate-500 tracking-wide uppercase">
              Content settings
            </p>
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm text-slate-800">Session reminders</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  Daily nudges to keep your learning streak going.
                </p>
              </div>
              <Toggle checked={aiDifficulty} onChange={setAiDifficulty} className="shrink-0" />
            </div>
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm text-slate-800">AI difficulty adaptation</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  Adjust content difficulty based on your performance.
                </p>
              </div>
              <Toggle checked={bilingualContent} onChange={setBilingualContent} className="shrink-0" />
            </div>
          </div>
        </div>
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
    </div>
  );
}
