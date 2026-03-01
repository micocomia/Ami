import { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { Button, Select } from '@/components/ui';
import { cn } from '@/lib/cn';

/* ------------------------------------------------------------------ */
/*  Mock data                                                         */
/* ------------------------------------------------------------------ */

const TIME_OPTIONS = ['Last 7 days', 'Last 30 days', 'All time'] as const;
type TimeRange = (typeof TIME_OPTIONS)[number];

const GOAL_OPTIONS = [
  { value: 'g1', label: 'Learn French for Travel' },
  { value: 'g2', label: 'Goal Name 2' },
  { value: 'g3', label: 'Goal Name 3' },
];

const OVERVIEW_KPIS = [
  { title: 'Total Sessions', value: '26', desc: 'Body text' },
  { title: 'Active Goals', value: '5', desc: 'Body text' },
  { title: 'At Risk', value: '--', desc: 'Body text' },
  { title: 'Best Performing', value: '--', desc: 'Body text' },
];

const ACTIVE_GOAL_KPIS = [
  { title: 'Overall Progress', value: '26%', desc: 'Body text' },
  { title: 'Quiz Performance', value: '5', desc: 'Body text' },
  { title: 'Skills Status', value: '4', desc: 'Body text' },
  { title: '--', value: '--', desc: 'Body text' },
];

const OVERVIEW_GOALS = [
  { id: '1', name: '[Goal name]', status: 'In progress' as const, progress: 50, topGap: '[Skills]', nextUp: '[module name]' },
  { id: '2', name: '[Goal name]', status: 'At Risk' as const, progress: 50, topGap: '[Skills]', nextUp: '[module name]' },
  { id: '3', name: '[Goal name]', status: 'In progress' as const, progress: 50, topGap: '[Skills]', nextUp: '[module name]' },
];

const SKILL_MASTERY_FILTERS = ['All', 'Gaps only', 'Mastered'] as const;
const SKILLS = [
  { id: '1', name: '[Skills name]', status: 'In progress' as const, current: 50, required: 80 },
  { id: '2', name: '[Skills name]', status: 'Not Started' as const, current: 10, required: 80 },
  { id: '3', name: '[Skills name]', status: 'Not Started' as const, current: 10, required: 80 },
  { id: '4', name: '[Skills name]', status: 'Completed' as const, current: 80, required: 80 },
];

function ClockIcon() {
  return (
    <svg className="w-5 h-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Overview view (Goals overview)                                    */
/* ------------------------------------------------------------------ */

function AnalyticsOverview() {
  const [timeRange, setTimeRange] = useState<TimeRange>('Last 30 days');
  const [activeTab, setActiveTab] = useState<'learning' | 'goals'>('learning');

  return (
    <div className="space-y-6">
      {/* Tabs + time filter */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex gap-1 border-b border-slate-200">
          <button
            type="button"
            onClick={() => setActiveTab('learning')}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              activeTab === 'learning'
                ? 'border-primary-600 text-primary-700'
                : 'border-transparent text-slate-500 hover:text-slate-700',
            )}
          >
            Learning Analytics
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('goals')}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              activeTab === 'goals'
                ? 'border-primary-600 text-primary-700'
                : 'border-transparent text-slate-500 hover:text-slate-700',
            )}
          >
            Goals overview
          </button>
        </div>
        <div className="flex gap-2">
          {TIME_OPTIONS.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => setTimeRange(opt)}
              className={cn(
                'text-sm font-medium px-3 py-1.5 rounded-md transition-colors',
                timeRange === opt ? 'bg-primary-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
              )}
            >
              {timeRange === opt ? '✔ ' : ''}{opt}
            </button>
          ))}
        </div>
      </div>

      {/* KPI cards + Next Step */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="lg:col-span-3 grid grid-cols-2 lg:grid-cols-4 gap-4">
          {OVERVIEW_KPIS.map((kpi) => (
            <div key={kpi.title} className="bg-white rounded-xl border border-slate-200 p-4">
              <ClockIcon />
              <p className="text-sm font-semibold text-slate-800 mt-2">{kpi.title}</p>
              <p className="text-xl font-bold text-slate-900 mt-0.5">{kpi.value}</p>
              <p className="text-xs text-slate-500 mt-1">{kpi.desc}</p>
            </div>
          ))}
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4 flex flex-col">
          <h3 className="text-sm font-semibold text-slate-800">Next Step</h3>
          <div className="flex-1 space-y-2 mt-3">
            <div className="h-2 bg-slate-200 rounded w-full" />
            <div className="h-2 bg-slate-200 rounded w-4/5" />
            <div className="h-2 bg-slate-200 rounded w-3/5" />
          </div>
          <div className="mt-4 flex justify-end">
            <Button size="sm" className="!bg-primary-600 hover:!bg-primary-700 !text-white" onClick={() => {}}>
              Continue Learning
            </Button>
          </div>
        </div>
      </div>

      {/* Goals overview list */}
      <section>
        <h3 className="text-base font-semibold text-slate-800 mb-4">Goals overview</h3>
        <div className="space-y-3">
          {OVERVIEW_GOALS.map((goal) => (
            <div
              key={goal.id}
              className="bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-4 hover:border-slate-300 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <p className="font-medium text-slate-900">{goal.name}</p>
                <span
                  className={cn(
                    'inline-block text-xs font-medium px-2 py-0.5 rounded-full mt-1',
                    goal.status === 'At Risk' ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800',
                  )}
                >
                  {goal.status}
                </span>
                <div className="mt-3 space-y-1 text-sm text-slate-600">
                  <div className="flex items-center gap-2">
                    <span>Overall Path Progress</span>
                    <div className="flex-1 h-1.5 max-w-32 rounded-full bg-slate-200 overflow-hidden">
                      <div className="h-full bg-primary-500" style={{ width: `${goal.progress}%` }} />
                    </div>
                    <span className="font-medium">{goal.progress}%</span>
                  </div>
                  <p>Top Gap: {goal.topGap}</p>
                  <p>Next Up: {goal.nextUp}</p>
                </div>
              </div>
              <Link to="/analytics/active-goal" className="shrink-0 p-2 text-slate-400 hover:text-slate-600" aria-label="View goal">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                </svg>
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* Chart placeholders */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h3 className="text-sm font-semibold text-slate-800 mb-4">Learning Activity Chart</h3>
          <div className="h-48 bg-slate-100 rounded-lg flex items-center justify-center text-slate-400 text-sm">
            Chart
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h3 className="text-sm font-semibold text-slate-800 mb-4">Chart</h3>
          <div className="h-48 bg-slate-100 rounded-lg flex items-center justify-center text-slate-400 text-sm">
            Chart
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Active Goal view                                                   */
/* ------------------------------------------------------------------ */

function AnalyticsActiveGoal() {
  const navigate = useNavigate();
  const [timeRange, setTimeRange] = useState<TimeRange>('Last 7 days');
  const [selectedGoalId, setSelectedGoalId] = useState(GOAL_OPTIONS[0].value);
  const [skillFilter, setSkillFilter] = useState<(typeof SKILL_MASTERY_FILTERS)[number]>('All');

  const selectedGoalLabel = GOAL_OPTIONS.find((g) => g.value === selectedGoalId)?.label ?? 'Goal 1';

  return (
    <div className="space-y-6">
      {/* Header: title + goal dropdown + time filter */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            to="/analytics"
            className="text-sm text-slate-500 hover:text-slate-700 flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
            Overview
          </Link>
          <h2 className="text-lg font-semibold text-slate-800">
            Learning Analytics <span className="text-slate-500 font-normal">[{selectedGoalLabel}]</span>
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="w-44">
            <Select
              options={GOAL_OPTIONS}
              value={selectedGoalId}
              onChange={(e) => setSelectedGoalId(e.target.value)}
              aria-label="Select goal"
              className="text-sm"
            />
          </div>
          <div className="flex gap-2">
            {TIME_OPTIONS.map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => setTimeRange(opt)}
                className={cn(
                  'text-sm font-medium px-3 py-1.5 rounded-md transition-colors',
                  timeRange === opt ? 'bg-primary-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                )}
              >
                {timeRange === opt ? '✔ ' : ''}{opt}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* KPI cards + Next Step */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="lg:col-span-3 grid grid-cols-2 lg:grid-cols-4 gap-4">
          {ACTIVE_GOAL_KPIS.map((kpi) => (
            <div key={kpi.title} className="bg-white rounded-xl border border-slate-200 p-4">
              <ClockIcon />
              <p className="text-sm font-semibold text-slate-800 mt-2">{kpi.title}</p>
              <p className="text-xl font-bold text-slate-900 mt-0.5">{kpi.value}</p>
              <p className="text-xs text-slate-500 mt-1">{kpi.desc}</p>
            </div>
          ))}
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4 flex flex-col">
          <h3 className="text-sm font-semibold text-slate-800">Next Step</h3>
          <div className="flex-1 space-y-2 mt-3">
            <div className="h-2 bg-slate-200 rounded w-full" />
            <div className="h-2 bg-slate-200 rounded w-4/5" />
            <div className="h-2 bg-slate-200 rounded w-3/5" />
          </div>
          <div className="mt-4 flex justify-end">
            <Button size="sm" className="!bg-primary-600 hover:!bg-primary-700 !text-white" onClick={() => navigate('/learning-session')}>
              Continue Learning
            </Button>
          </div>
        </div>
      </div>

      {/* Skill mastery */}
      <section className="bg-white rounded-xl border border-slate-200 p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-4">
          <h3 className="text-base font-semibold text-slate-800">Skill mastery</h3>
          <div className="flex gap-2">
            {SKILL_MASTERY_FILTERS.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setSkillFilter(f)}
                className={cn(
                  'text-sm font-medium px-3 py-1.5 rounded-md transition-colors',
                  skillFilter === f ? 'bg-primary-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                )}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        <ul className="space-y-3">
          {SKILLS.map((skill) => (
            <li key={skill.id} className="flex flex-col sm:flex-row sm:items-center gap-3 py-3 border-b border-slate-100 last:border-0">
              <span className="font-medium text-slate-900 sm:w-40">{skill.name}</span>
              <span
                className={cn(
                  'text-xs font-medium px-2 py-0.5 rounded-full w-fit',
                  skill.status === 'In progress' && 'bg-slate-100 text-slate-700',
                  skill.status === 'Not Started' && 'bg-slate-100 text-slate-600',
                  skill.status === 'Completed' && 'bg-slate-200 text-slate-800',
                )}
              >
                {skill.status}
              </span>
              <div className="flex-1 flex items-center gap-2">
                <span className="text-sm text-slate-500 w-24 shrink-0">Mastery Progress</span>
                <div className="flex-1 max-w-xs h-2 rounded-full bg-slate-200 overflow-hidden">
                  <div
                    className="h-full bg-primary-500 rounded-full transition-all"
                    style={{ width: `${(skill.current / skill.required) * 100}%` }}
                  />
                </div>
                <span className="text-sm text-slate-600 whitespace-nowrap">
                  {skill.current}%/{skill.required}% required
                </span>
              </div>
              <Button variant="secondary" size="sm">
                Practice
              </Button>
            </li>
          ))}
        </ul>
      </section>

      {/* Skill Radar placeholder */}
      <section className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-base font-semibold text-slate-800 mb-4">Skill Radar</h3>
        <div className="h-64 bg-slate-100 rounded-lg flex items-center justify-center text-slate-400 text-sm">
          [Skill] radar chart placeholder
        </div>
      </section>

      {/* Learning Activity Chart placeholders */}
      <section>
        <h3 className="text-base font-semibold text-slate-800 mb-4">Learning Activity Chart</h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="h-48 bg-slate-100 rounded-lg flex items-center justify-center text-slate-400 text-sm border border-slate-200">
            Chart
          </div>
          <div className="h-48 bg-slate-100 rounded-lg flex items-center justify-center text-slate-400 text-sm border border-slate-200">
            Chart
          </div>
        </div>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export function AnalyticsPage() {
  const location = useLocation();
  const isActiveGoalView = location.pathname === '/analytics/active-goal';

  return (
    <div className="max-w-5xl mx-auto">
      {isActiveGoalView ? <AnalyticsActiveGoal /> : <AnalyticsOverview />}
    </div>
  );
}
