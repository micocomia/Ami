import { Link } from 'react-router-dom';
import { Button } from '@/components/ui';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/context/GoalsContext';
import { useDashboardMetrics } from '@/api/endpoints/content';
import { useBehavioralMetrics } from '@/api/endpoints/metrics';
import { useBiasAuditHistory } from '@/api/endpoints/skillGap';
import { HighRiskBanner } from '@/components/analytics';

function formatDuration(secs: number | undefined): string {
  if (!secs || !Number.isFinite(secs)) return '—';
  if (secs < 60) return `${Math.round(secs)}s`;
  if (secs < 3600) return `${Math.round(secs / 60)}m`;
  const h = Math.floor(secs / 3600);
  const m = Math.round((secs % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

const quickLinks = [
  { to: '/goals', label: 'Set Learning Goals', description: 'Define and refine what you want to learn.' },
  { to: '/learning-path', label: 'Learning Path', description: 'View your personalized study schedule.' },
];

export function HomePage() {
  const { userId } = useAuthContext();
  const { goals } = useGoalsContext();
  const { activeGoal } = useActiveGoal();
  const { data: metrics, isLoading: dashLoading } = useDashboardMetrics(
    userId ?? undefined,
    activeGoal?.id,
  );
  const {
    data: behavMetrics,
    isLoading: behavLoading,
    error: behavError,
  } = useBehavioralMetrics(userId ?? undefined, activeGoal?.id);
  const { data: biasHistory } = useBiasAuditHistory(userId ?? undefined);
  const isLoading = dashLoading || behavLoading;

  const overallProgressPct = (() => {
    const raw = metrics?.overall_progress;
    if (typeof raw !== 'number' || !Number.isFinite(raw)) return '—';
    // Backend may return 0–1 or 0–100. Normalize to 0–100.
    const normalized = raw <= 1 ? raw * 100 : raw;
    const clamped = Math.min(Math.max(normalized, 0), 100);
    return `${Math.round(clamped)}%`;
  })();

  const sessionsCompleted = (() => {
    if (behavMetrics && typeof behavMetrics.sessions_completed === 'number') {
      return `${behavMetrics.sessions_completed} / ${behavMetrics.total_sessions_in_path}`;
    }
    if (activeGoal?.learning_path) {
      const done = activeGoal.learning_path.filter((s) => s.if_learned).length;
      return `${done} / ${activeGoal.learning_path.length}`;
    }
    return '—';
  })();

  const hasActiveContext = Boolean(userId && activeGoal);
  const totalStudyTimeState = (() => {
    if (!hasActiveContext) {
      return { main: 'No active goal', helper: '' };
    }
    if (behavError) {
      return { main: 'Unavailable', helper: 'Try again later' };
    }
    const secs = behavMetrics?.total_learning_time_sec;
    if (typeof secs === 'number' && secs > 0) {
      return { main: formatDuration(secs), helper: '' };
    }
    // Active goal but no learning time yet
    return {
      main: 'No study time yet',
      helper: 'Complete a session to see your study time',
    };
  })();

  return (
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 space-y-8">
      {/* High-risk bias warning */}
      <HighRiskBanner entries={biasHistory?.entries ?? []} />

      {/* Welcome banner — colors: bg #D9EEF1, title #12333A, body #355C63, button #FFF / #0F5968 */}
      <div className="rounded-xl p-8 bg-[#D9EEF1]">
        <h2 className="text-2xl font-bold text-[#12333A]">Welcome back!</h2>
        <p className="mt-2 max-w-lg text-[#355C63]">
          Pick up where you left off, or start something new. Ami adapts your learning path based on your progress.
        </p>
        <Link to="/goals">
          <Button
            variant="secondary"
            className="mt-5 !bg-[#FFFFFF] !text-[#0F5968] border-0 shadow-sm hover:!bg-[#F0F7F8] hover:!text-[#0F5968]"
          >
            Continue Learning
          </Button>
        </Link>
      </div>

      {/* Lightweight dashboard summary */}
      <section>
        <h3 className="text-lg font-semibold text-slate-800 mb-3">Your learning at a glance</h3>
        {(!activeGoal || !userId) && !isLoading ? (
          <p className="text-sm text-slate-500">
            Start a learning goal to see your dashboard stats here.
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {isLoading
              ? [1, 2, 3, 4].map((i) => (
                  <div key={i} className="h-20 bg-slate-100 rounded-xl animate-pulse" />
                ))
              : (
                <>
                  <div className="bg-white rounded-xl border border-slate-200 p-4">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Active Goal</p>
                    <p className="mt-1 text-sm font-medium text-slate-900 line-clamp-2">
                      {activeGoal
                        ? ((activeGoal.learner_profile?.goal_display_name as string | undefined) ??
                          activeGoal.learning_goal)
                        : 'No active goal'}
                    </p>
                  </div>
                  <div className="bg-white rounded-xl border border-slate-200 p-4">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Overall Progress</p>
                    <p className="mt-1 text-2xl font-bold text-slate-900">{overallProgressPct}</p>
                  </div>
                  <div className="bg-white rounded-xl border border-slate-200 p-4">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Sessions Completed</p>
                    <p className="mt-1 text-2xl font-bold text-slate-900">{sessionsCompleted}</p>
                  </div>
                  <div className="bg-white rounded-xl border border-slate-200 p-4">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                      Total Study Time
                    </p>
                    <p className="mt-1 text-2xl font-bold text-slate-900">
                      {totalStudyTimeState.main}
                    </p>
                    {totalStudyTimeState.helper && (
                      <p className="mt-1 text-xs text-slate-500">
                        {totalStudyTimeState.helper}
                      </p>
                    )}
                    <p className="mt-1 text-xs text-slate-500">Goals: {goals.length}</p>
                  </div>
                </>
              )}
          </div>
        )}
      </section>

      {/* Quick-access cards */}
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Quick Access</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {quickLinks.map(({ to, label, description }) => (
            <Link
              key={to}
              to={to}
              className="group block bg-white rounded-lg border border-slate-200 p-5 hover:border-primary-300 hover:shadow-md transition-all"
            >
              <h4 className="font-medium text-slate-800 group-hover:text-primary-600 transition-colors">
                {label}
              </h4>
              <p className="mt-1 text-sm text-slate-500 leading-relaxed">{description}</p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
