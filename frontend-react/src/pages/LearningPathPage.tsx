import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui';
import { Select } from '@/components/ui';
import { cn } from '@/lib/cn';
import { MOCK_GOALS, MOCK_SESSIONS } from '@/mock/learningPath';

/* ------------------------------------------------------------------ */
/*  Derived constants                                                 */
/* ------------------------------------------------------------------ */

const totalSessions = MOCK_SESSIONS.length;
const completedCount = MOCK_SESSIONS.filter((s) => s.status === 'completed').length;
const progressPct = totalSessions > 0 ? Math.round((completedCount / totalSessions) * 100) : 0;

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export function LearningPathPage() {
  const navigate = useNavigate();
  const [selectedGoalId, setSelectedGoalId] = useState(MOCK_GOALS[0].id);
  const selectedGoal = MOCK_GOALS.find((g) => g.id === selectedGoalId) ?? MOCK_GOALS[0];

  const handleStartSession = (sessionId: string) => {
    navigate('/learning-session', { state: { sessionId } });
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header: Current goal + Goal dropdown */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <p className="text-base font-medium text-slate-800">
          Current Goal: <span className="text-slate-900">{selectedGoal.name}</span>
        </p>
        <div className="flex items-center gap-3">
          <div className="w-48">
            <Select
              options={MOCK_GOALS.map((g) => ({ value: g.id, label: g.name }))}
              value={selectedGoalId}
              onChange={(e) => setSelectedGoalId(e.target.value)}
              className="text-sm"
              aria-label="Select goal"
            />
          </div>
          <Button variant="secondary" size="sm" className="shrink-0">
            <svg className="w-4 h-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Simulate AI Update
          </Button>
        </div>
      </div>

      {/* Two columns: Session list | Overall Progress */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Session list */}
        <div className="flex-1 space-y-3">
          {MOCK_SESSIONS.map((session) => (
            <div
              key={session.id}
              className="bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-4"
            >
              {/* Number or # circle */}
              <div
                className={cn(
                  'w-12 h-12 rounded-full flex items-center justify-center shrink-0 text-lg font-bold',
                  session.status === 'completed' ? 'bg-slate-200 text-slate-700' : 'bg-slate-100 text-slate-500',
                )}
              >
                {session.status === 'locked' ? '#' : session.index}
              </div>

              {/* Title + tags */}
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-slate-900 truncate">
                  Session {session.index} {session.title}
                </h3>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {session.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-500"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>

              {/* Status / action */}
              <div className="shrink-0">
                {session.status === 'completed' && (
                  <span className="text-sm text-slate-500 font-medium">Completed</span>
                )}
                {session.status === 'startable' && (
                  <Button
                    variant="secondary"
                    size="sm"
                    className="!bg-primary-600 !text-white hover:!bg-primary-700"
                    onClick={() => handleStartSession(session.id)}
                  >
                    <svg className="w-4 h-4 mr-1.5" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M8 5.14v14l11-7-11-7z" />
                    </svg>
                    Start
                  </Button>
                )}
                {session.status === 'locked' && (
                  <span className="text-sm text-slate-400 font-medium px-3 py-1.5 rounded-md bg-slate-100">
                    Locked
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Overall Progress card */}
        <div className="lg:w-72 shrink-0">
          <div className="bg-white rounded-xl border border-slate-200 p-5 sticky top-4">
            <h3 className="text-sm font-semibold text-slate-800 mb-3">Overall Progress</h3>
            <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
              <div
                className="h-full rounded-full bg-primary-500 transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <p className="mt-2 text-sm text-slate-500">
              {completedCount} of {totalSessions} sessions completed
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
