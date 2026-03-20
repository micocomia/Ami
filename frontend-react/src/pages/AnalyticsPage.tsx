import { useLocation } from 'react-router-dom';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/hooks/useActiveGoal';
import { useDashboardMetrics } from '@/api/endpoints/content';
import { useBiasAuditHistory } from '@/api/endpoints/skillGap';
import { SkillRadarChart, SessionTimeChart, MasteryChart, BiasRiskTrendChart, RecentAuditsTable, HighRiskBanner } from '@/components/analytics';
import { Select } from '@/components/ui';

/* ------------------------------------------------------------------ */
/*  Active Goal view                                                   */
/* ------------------------------------------------------------------ */

function AnalyticsActiveGoal() {
  const { userId } = useAuthContext();
  const { goals, selectedGoalId, setSelectedGoalId } = useGoalsContext();
  const activeGoal = useActiveGoal();

  const { data: metrics, isLoading } = useDashboardMetrics(
    userId ?? undefined,
    activeGoal?.id,
  );

  const { data: biasHistory } = useBiasAuditHistory(userId ?? undefined, activeGoal?.id);

  const goalOptions = goals.map((g) => ({
    value: String(g.id),
    label: (g.learner_profile?.goal_display_name ?? g.learning_goal).slice(0, 50),
  }));

  const overallProgress = metrics?.overall_progress ?? 0;
  const sessionsCompleted = (activeGoal?.learning_path ?? []).filter(
    (s: { if_learned?: boolean }) => s.if_learned,
  ).length;
  const totalSessions = activeGoal?.learning_path?.length ?? 0;
  const skillsTracked = metrics?.skill_radar?.labels?.length ?? 0;

  return (
    <div className="space-y-6">
      {/* High-risk bias warning */}
      <HighRiskBanner entries={biasHistory?.entries ?? []} />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h2 className="text-xl font-semibold text-slate-800">Learning Analytics</h2>
        {goalOptions.length > 1 && (
          <div className="w-56">
            <Select
              options={goalOptions}
              value={String(selectedGoalId ?? '')}
              onChange={(e) => setSelectedGoalId(Number(e.target.value))}
              aria-label="Select goal"
              className="text-sm"
            />
          </div>
        )}
      </div>

      {/* KPI cards */}
      {isLoading ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { title: 'Overall Progress', value: `${Math.round(overallProgress * 100)}%` },
            { title: 'Active Goals', value: String(goals.length) },
            { title: 'Sessions Completed', value: `${sessionsCompleted} / ${totalSessions}` },
            { title: 'Skills Tracked', value: String(skillsTracked) },
          ].map(({ title, value }) => (
            <div key={title} className="bg-white rounded-xl border border-slate-200 p-4">
              <p className="text-sm font-medium text-slate-500">{title}</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Skill Radar */}
      {metrics?.skill_radar && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <h3 className="font-semibold text-slate-700 mb-4">Skill Radar</h3>
          <SkillRadarChart
            labels={metrics.skill_radar.labels}
            currentLevels={metrics.skill_radar.current_levels}
            requiredLevels={metrics.skill_radar.required_levels}
          />
        </div>
      )}

      {/* Session Time + Mastery */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {metrics?.session_time_series && metrics.session_time_series.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h3 className="font-semibold text-slate-700 mb-4">Time per Session</h3>
            <SessionTimeChart data={metrics.session_time_series} />
          </div>
        )}
        {metrics?.mastery_time_series && metrics.mastery_time_series.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h3 className="font-semibold text-slate-700 mb-4">Mastery Over Time</h3>
            <MasteryChart data={metrics.mastery_time_series} />
          </div>
        )}
      </div>

      {/* Bias & Ethics Review */}
      {biasHistory && biasHistory.entries.length > 0 && (
        <>
          <h3 className="text-lg font-semibold text-slate-800 mt-2">Bias & Ethics Review</h3>

          {/* Bias KPI cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <p className="text-sm font-medium text-slate-500">Total Audits</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">{biasHistory.summary.total_audits}</p>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <p className="text-sm font-medium text-slate-500">Total Flags</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">{biasHistory.summary.total_flags}</p>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <p className="text-sm font-medium text-slate-500">Current Risk</p>
              <p className={`text-2xl font-bold mt-1 capitalize ${
                biasHistory.summary.current_risk === 'low' ? 'text-green-600' :
                biasHistory.summary.current_risk === 'medium' ? 'text-amber-600' :
                'text-red-600'
              }`}>
                {biasHistory.summary.current_risk}
              </p>
            </div>
          </div>

          {/* Trend chart + Recent Audits table */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h4 className="font-semibold text-slate-700 mb-4">Risk Level Over Time</h4>
              <BiasRiskTrendChart entries={biasHistory.entries} />
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h4 className="font-semibold text-slate-700 mb-4">Recent Audits</h4>
              <RecentAuditsTable entries={biasHistory.entries} />
            </div>
          </div>
        </>
      )}

      {!isLoading && !metrics && (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
          <p className="text-slate-400 text-sm">
            No analytics data yet. Complete some sessions to see your progress.
          </p>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export function AnalyticsPage() {
  // Both /analytics and /analytics/active-goal render the same view
  useLocation();

  return (
    <div className="max-w-5xl mx-auto">
      <AnalyticsActiveGoal />
    </div>
  );
}
