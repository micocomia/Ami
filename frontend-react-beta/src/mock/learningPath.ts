/**
 * Shared mock data for Learning Path and Learning Session pages.
 * Keeps session list, titles, and goal in one place so both pages stay in sync.
 */

export interface Goal {
  id: string;
  name: string;
}

export type SessionStatus = 'completed' | 'startable' | 'locked';

export interface SessionItem {
  id: string;
  index: number;
  title: string;
  tags: string[];
  status: SessionStatus;
}

export const BREADCRUMB_GOAL = 'Learn French for Travel';

export const MOCK_GOALS: Goal[] = [
  { id: 'goal1', name: 'I want to learn French' },
  { id: 'goal2', name: 'Goal Name 2' },
  { id: 'goal3', name: 'Goal Name 3' },
];

export const MOCK_SESSIONS: SessionItem[] = [
  { id: 's1', index: 1, title: 'Greetings & Phrases', tags: ['Tag', 'Tag'], status: 'completed' },
  { id: 's2', index: 2, title: 'Numbers, Dates & Time', tags: ['Tag', 'Tag'], status: 'startable' },
  { id: 's3', index: 3, title: 'Shopping & Dining', tags: ['Tag', 'Tag'], status: 'locked' },
  { id: 's4', index: 4, title: 'Directions & Transport', tags: ['Tag', 'Tag'], status: 'locked' },
  { id: 's5', index: 5, title: 'Accommodation', tags: ['Tag', 'Tag'], status: 'locked' },
  { id: 's6', index: 6, title: 'Emergencies & Health', tags: ['Tag', 'Tag'], status: 'locked' },
];

/** Session id that has full module content in LearningSessionPage (Session 2 = Numbers, Dates & Time). */
export const DEFAULT_SESSION_ID = 's2';

export function getSessionById(sessionId: string): SessionItem | undefined {
  return MOCK_SESSIONS.find((s) => s.id === sessionId);
}
