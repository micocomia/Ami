import type { NavigateFunction } from 'react-router-dom';
import { listGoalsApi } from '@/api/endpoints/goals';

/**
 * After login/register: GET /v1/goals/{user_id}.
 * If user has goals → goal management (/goals); otherwise onboarding.
 */
export async function navigateAfterAuth(navigate: NavigateFunction, userId: string): Promise<void> {
  try {
    const res = await listGoalsApi(userId);
    const active = (res.goals ?? []).filter((g) => !g.is_deleted);
    if (active.length > 0) {
      navigate('/goals', { replace: true });
    } else {
      navigate('/onboarding', { replace: true });
    }
  } catch {
    // API error: send to onboarding so new users can complete flow
    navigate('/onboarding', { replace: true });
  }
}
