import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui';
import { FslsmSliders } from '@/components/profile/FslsmSliders';
import { EditProfileModal } from '@/components/profile/EditProfileModal';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/hooks/useActiveGoal';
import { useAppConfig } from '@/api/endpoints/config';
import { useBehavioralMetrics } from '@/api/endpoints/metrics';
import { useDeleteUserData } from '@/api/endpoints/content';
import { useDeleteUser } from '@/api/endpoints/auth';

function formatDuration(secs: number): string {
  if (secs < 60) return `${Math.round(secs)}s`;
  if (secs < 3600) return `${Math.round(secs / 60)}m`;
  const h = Math.floor(secs / 3600);
  const m = Math.round((secs % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

export function ProfilePage() {
  const navigate = useNavigate();
  const { userId, logout } = useAuthContext();
  const { refreshGoals, updateGoal } = useGoalsContext();
  const activeGoal = useActiveGoal();
  const { data: config } = useAppConfig();

  const { data: metrics, isLoading: metricsLoading } = useBehavioralMetrics(
    userId ?? undefined,
    activeGoal?.id,
  );

  const deleteUserDataMutation = useDeleteUserData();
  const deleteUserMutation = useDeleteUser();

  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteDataConfirm, setShowDeleteDataConfirm] = useState(false);
  const [showDeleteAccountConfirm, setShowDeleteAccountConfirm] = useState(false);

  const fairness = activeGoal?.profile_fairness as Record<string, unknown> | undefined;
  const fairnessRisk = fairness?.overall_fairness_risk as string | undefined;
  const fairnessFlags = fairness?.flags as string[] | undefined;
  const showFairnessWarning = fairnessRisk === 'medium' || fairnessRisk === 'high';

  const fslsmDims = (activeGoal?.learner_profile?.learning_preferences?.fslsm_dimensions as Record<string, number> | undefined) ?? {};

  const handleRestartOnboarding = async () => {
    if (!userId) return;
    try {
      await deleteUserDataMutation.mutateAsync(userId);
      refreshGoals();
      navigate('/onboarding');
    } catch { /* ignore */ }
    setShowDeleteDataConfirm(false);
  };

  const handleDeleteAccount = async () => {
    if (!userId) return;
    try {
      await deleteUserMutation.mutateAsync();
      logout();
      navigate('/login');
    } catch { /* ignore */ }
    setShowDeleteAccountConfirm(false);
  };

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-800">My Profile</h2>
          <p className="mt-0.5 text-sm text-slate-500">@{userId}</p>
        </div>
        <div className="flex gap-2">
          {activeGoal && (
            <Button size="sm" onClick={() => setShowEditModal(true)}>Edit Profile</Button>
          )}
          <Button size="sm" variant="secondary" onClick={() => { logout(); navigate('/login'); }}>
            Logout
          </Button>
        </div>
      </div>

      {/* Behavioural metrics */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <h3 className="font-semibold text-slate-700 mb-4">Learning Progress</h3>
        {metricsLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-16 bg-slate-100 rounded-lg animate-pulse" />
            ))}
          </div>
        ) : metrics ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            {[
              { label: 'Sessions Completed', value: `${metrics.sessions_completed} / ${metrics.total_sessions_in_path}` },
              { label: 'Avg Session Duration', value: formatDuration(metrics.avg_session_duration_sec) },
              { label: 'Total Learning Time', value: formatDuration(metrics.total_learning_time_sec) },
              { label: 'Latest Mastery Rate', value: metrics.latest_mastery_rate != null ? `${Math.round(metrics.latest_mastery_rate * 100)}%` : '—' },
              { label: 'Sessions Learned', value: String(metrics.sessions_learned) },
              { label: 'Motivational Triggers', value: String(metrics.motivational_triggers_count) },
            ].map(({ label, value }) => (
              <div key={label} className="bg-slate-50 rounded-lg p-3">
                <p className="text-xs text-slate-500 mb-1">{label}</p>
                <p className="font-semibold text-slate-800">{value}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-400">No metrics available yet.</p>
        )}
      </div>

      {/* FSLSM sliders */}
      {Object.keys(fslsmDims).length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <h3 className="font-semibold text-slate-700 mb-4">Learning Style (FSLSM)</h3>
          <FslsmSliders values={fslsmDims} config={config} />
        </div>
      )}

      {/* Fairness banner */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
        <h3 className="font-semibold text-slate-700">Fairness & Ethics</h3>
        <p className="text-xs text-slate-500">
          Ami uses AI to generate personalised content. Assessments are estimates and may not fully
          reflect your actual abilities. All AI outputs should be critically evaluated.
        </p>
        {showFairnessWarning && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
            Fairness risk level: <strong className="capitalize">{fairnessRisk}</strong>. Some aspects of your
            learning profile may benefit from additional review.
          </div>
        )}
        {fairnessFlags && fairnessFlags.length > 0 && (
          <details className="text-sm border border-slate-200 rounded-lg">
            <summary className="px-4 py-2 cursor-pointer text-slate-600 font-medium select-none">
              Fairness flags ({fairnessFlags.length})
            </summary>
            <ul className="px-4 pb-3 pt-1 space-y-1 text-xs text-slate-500 list-disc list-inside">
              {fairnessFlags.map((flag, i) => <li key={i}>{flag}</li>)}
            </ul>
          </details>
        )}
      </div>

      {/* Account actions */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
        <h3 className="font-semibold text-slate-700">Account</h3>

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
              <Button size="sm" onClick={handleRestartOnboarding} loading={deleteUserDataMutation.isPending}
                className="!bg-amber-600 hover:!bg-amber-700 !text-white">
                Yes, restart
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setShowDeleteDataConfirm(false)}>Cancel</Button>
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
              <Button size="sm" onClick={handleDeleteAccount} loading={deleteUserMutation?.isPending}
                className="!bg-red-600 hover:!bg-red-700 !text-white">
                Delete account
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setShowDeleteAccountConfirm(false)}>Cancel</Button>
            </div>
          </div>
        )}
      </div>

      {/* Edit Profile Modal */}
      {showEditModal && activeGoal && userId && (
        <EditProfileModal
          activeGoal={activeGoal}
          userId={userId}
          onClose={() => setShowEditModal(false)}
          onUpdate={(updatedGoal) => {
            updateGoal(activeGoal.id, updatedGoal);
          }}
        />
      )}
    </div>
  );
}
