/**
 * Backend auth/me currently may only return username. We persist the first time
 * we see a successful login/register per user so Profile can show "Member since".
 * If auth/me later returns created_at, Profile should prefer that.
 */
const STORAGE_PREFIX = 'ami_member_since_';

function storageKey(userId: string): string {
  return `${STORAGE_PREFIX}${userId}`;
}

/** Call after successful login/register so Member since has a real anchor. */
export function ensureMemberSinceRecorded(userId: string): void {
  if (!userId) return;
  try {
    const key = storageKey(userId);
    if (localStorage.getItem(key)) return;
    localStorage.setItem(key, new Date().toISOString());
  } catch {
    // ignore
  }
}

/** ISO string or null if never recorded */
export function getMemberSinceIso(userId: string | null): string | null {
  if (!userId) return null;
  try {
    return localStorage.getItem(storageKey(userId));
  } catch {
    return null;
  }
}

export function formatMemberSinceDisplay(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

/** Parse date from goal aggregate if API sends created_at / createdAt */
export function earliestGoalTimestampIso(goals: Array<Record<string, unknown>>): string | null {
  let best: number | null = null;
  for (const g of goals) {
    const v = g.created_at ?? g.createdAt ?? g.created_at_ms;
    if (v == null) continue;
    const t =
      typeof v === 'number'
        ? v
        : typeof v === 'string'
          ? Date.parse(v)
          : NaN;
    if (Number.isFinite(t) && (best == null || t < best)) best = t;
  }
  if (best == null) return null;
  return new Date(best).toISOString();
}
