import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Toggle } from '@/components/ui';

/* ------------------------------------------------------------------ */
/*  Mock data                                                         */
/* ------------------------------------------------------------------ */

const PROFILE = {
  name: 'Name',
  email: 'demo@genmentor.ai',
  memberSince: 'February 2026',
  plan: 'Free',
  tags: ['Visual Learner', 'Balanced'],
};

const ACTIVITY = {
  goalsCreated: 4,
  sessionsCompleted: 12,
  totalStudyTime: '8.5 hrs',
  currentStreak: 5,
  quizzesPassed: '9/12',
};

const TALENT_FILE = {
  name: 'Resume_Alex_Johnson_2028.pdf',
  size: '142 KB',
  lastUpdated: 'Feb 10',
};

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export function ProfilePage() {
  const [learningStyle, setLearningStyle] = useState('Visual Learner');
  const [aiDifficulty, setAiDifficulty] = useState(true);
  const [bilingualContent, setBilingualContent] = useState(false);

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
          <h2 className="text-lg font-semibold text-slate-900">{PROFILE.name}</h2>
          <div className="flex flex-wrap gap-2 mt-2">
            {PROFILE.tags.map((tag) => (
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
          <Link
            to="#"
            className="text-sm font-medium text-slate-700 hover:text-slate-900 transition-colors"
          >
            Edit Profile
          </Link>
          <Link
            to="/login"
            className="text-sm font-medium text-slate-700 hover:text-slate-900 transition-colors"
          >
            Sign out
          </Link>
        </div>
      </section>

      {/* Grid: Account | Activity | Preferences */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ACCOUNT */}
        <section className="bg-white rounded-xl border border-slate-200 p-5">
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Account</h3>
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-slate-500 font-medium">Email</dt>
              <dd className="text-slate-900 mt-0.5">{PROFILE.email}</dd>
            </div>
            <div>
              <dt className="text-slate-500 font-medium">Member since</dt>
              <dd className="text-slate-900 mt-0.5">{PROFILE.memberSince}</dd>
            </div>
            <div>
              <dt className="text-slate-500 font-medium">Plan</dt>
              <dd className="mt-0.5 flex items-center gap-2">
                <span className="text-slate-900">{PROFILE.plan}</span>
                <Link to="#" className="text-slate-600 hover:text-slate-900 font-medium text-xs">
                  Upgrade →
                </Link>
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
              <dd className="text-slate-900 font-medium">{ACTIVITY.goalsCreated}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Sessions completed</dt>
              <dd className="text-slate-900 font-medium">{ACTIVITY.sessionsCompleted}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Total study time</dt>
              <dd className="text-slate-900 font-bold">{ACTIVITY.totalStudyTime}</dd>
            </div>
            <div className="flex justify-between items-center">
              <dt className="text-slate-500">Current streak</dt>
              <dd className="text-slate-900 font-bold flex items-center gap-1">
                <span className="text-amber-500" aria-hidden>🔥</span>
                {ACTIVITY.currentStreak} days
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Quizzes passed</dt>
              <dd className="text-slate-900 font-medium">{ACTIVITY.quizzesPassed}</dd>
            </div>
          </dl>
        </section>

        {/* LEARNING PREFERENCES */}
        <section className="bg-white rounded-xl border border-slate-200 p-5">
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Learning Preferences</h3>
          <div className="space-y-5">
            {/* Presentation style */}
            <div className="space-y-2">
              <p className="text-xs font-semibold text-slate-500 tracking-wide uppercase">
                Presentation style
              </p>
              <div className="inline-flex w-full rounded-2xl bg-primary-50 p-1 border border-primary-100">
                {['Visual Learner', 'Balanced', 'Text-first'].map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setLearningStyle(option)}
                    className={`flex-1 px-4 py-2 text-sm font-medium rounded-2xl transition-all ${
                      learningStyle === option
                        ? 'bg-primary-600 text-white shadow-sm'
                        : 'text-primary-700 hover:text-primary-900'
                    }`}
                  >
                    {option}
                  </button>
                ))}
              </div>
              <p className="text-xs text-slate-500 italic mt-1">
                Prioritize detailed reading and scripts.
              </p>
            </div>

            {/* Content settings */}
            <div className="space-y-3 pt-2 border-t border-slate-100">
              <p className="text-xs font-semibold text-slate-500 tracking-wide uppercase">
                Content settings
              </p>
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-800">Smart difficulty</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Auto-adjust session level based on your performance.
                  </p>
                </div>
                <Toggle checked={aiDifficulty} onChange={setAiDifficulty} className="shrink-0" />
              </div>
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-800">English support</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Show key phrases with English side by side.
                  </p>
                </div>
                <Toggle checked={bilingualContent} onChange={setBilingualContent} className="shrink-0" />
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* TALENT ASSETS */}
      <section className="bg-white rounded-xl border border-slate-200 p-5">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Talent Assets</h3>
        <div className="border border-slate-200 rounded-lg p-4 bg-slate-50 flex items-center gap-4">
          <div className="w-12 h-12 rounded-lg bg-slate-200 flex items-center justify-center shrink-0">
            <svg className="w-6 h-6 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-900 truncate">{TALENT_FILE.name}</p>
            <p className="text-xs text-slate-500 mt-0.5">{TALENT_FILE.size} · Last updated {TALENT_FILE.lastUpdated}</p>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <Link to="#" className="text-sm font-medium text-slate-700 hover:text-slate-900">
              Update
            </Link>
            <button type="button" className="text-sm font-medium text-slate-700 hover:text-slate-900">
              Remove
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
