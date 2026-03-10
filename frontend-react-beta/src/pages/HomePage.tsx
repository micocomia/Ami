import { Link } from 'react-router-dom';
import { Button } from '@/components/ui';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/context/GoalsContext';
import { useDashboardMetrics } from '@/api/endpoints/content';

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
  const { data: metrics, isLoading } = useDashboardMetrics(userId ?? undefined, activeGoal?.id);

  const overallProgressPct =
    metrics && typeof metrics.overall_progress === 'number'
      ? `${Math.round(metrics.overall_progress * 100)}%`
      : '—';
  const sessionsCompleted =
    metrics && typeof metrics.sessions_completed === 'number'
      ? `${metrics.sessions_completed} / ${metrics.total_sessions_in_path}`
      : '—';
  const totalStudyTime = metrics ? formatDuration(metrics.total_learning_time_sec) : '—';

  return (
    <div className="space-y-8">
      {/* Welcome banner */}
      <div className="bg-gradient-to-br from-primary-400 to-primary-600 rounded-xl p-8 text-white">
        <h2 className="text-2xl font-bold">Welcome back!</h2>
        <p className="mt-2 text-primary-100 max-w-lg">
          Pick up where you left off, or start something new. Ami adapts your learning path based on your progress.
        </p>
        <Link to="/goals">
          <Button variant="secondary" className="mt-5 !text-primary-800 !bg-white/90 hover:!bg-white">
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
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Total Study Time</p>
                    <p className="mt-1 text-2xl font-bold text-slate-900">{totalStudyTime}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      Goals: {goals.length}
                    </p>
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
