import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuthContext } from './AuthContext';
import { listGoalsApi, goalsKeys } from '@/api/endpoints/goals';
import { syncProfileApi } from '@/api/endpoints/profile';
import type { GoalAggregate } from '@/types';

const SELECTED_GOAL_KEY = 'ami_selected_goal_id';

function readStoredGoalId(): number | null {
  try {
    const v = sessionStorage.getItem(SELECTED_GOAL_KEY);
    return v ? parseInt(v, 10) : null;
  } catch {
    return null;
  }
}

interface GoalsContextValue {
  goals: GoalAggregate[];
  selectedGoalId: number | null;
  setSelectedGoalId(id: number): void;
  refreshGoals(): void;
  updateGoal(goalId: number, goal: GoalAggregate): void;
  isLoading: boolean;
}

const GoalsContext = createContext<GoalsContextValue | null>(null);

export function GoalsProvider({ children }: { children: React.ReactNode }) {
  const { userId, isAuthenticated } = useAuthContext();
  const queryClient = useQueryClient();
  const [goals, setGoals] = useState<GoalAggregate[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedGoalId, setSelectedGoalIdState] = useState<number | null>(readStoredGoalId);

  // Fetch goals whenever userId changes
  useEffect(() => {
    if (!userId || !isAuthenticated) {
      setGoals([]);
      setSelectedGoalIdState(null);
      return;
    }
    setIsLoading(true);
    listGoalsApi(userId)
      .then((res) => {
        const active = res.goals.filter((g) => !g.is_deleted);
        setGoals(active);
        // Restore or default selectedGoalId
        setSelectedGoalIdState((prev) => {
          if (prev != null && active.some((g) => g.id === prev)) return prev;
          const first = active[0]?.id ?? null;
          if (first != null) {
            try { sessionStorage.setItem(SELECTED_GOAL_KEY, String(first)); } catch { /* ignore */ }
          }
          return first;
        });
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [userId, isAuthenticated]);

  const refreshGoals = useCallback(() => {
    if (!userId) return;
    queryClient.invalidateQueries({ queryKey: goalsKeys.list(userId) });
    setIsLoading(true);
    listGoalsApi(userId)
      .then((res) => {
        const active = res.goals.filter((g) => !g.is_deleted);
        setGoals(active);
        setSelectedGoalIdState((prev) => {
          if (prev != null && active.some((g) => g.id === prev)) return prev;
          return active[0]?.id ?? null;
        });
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [userId, queryClient]);

  const setSelectedGoalId = useCallback((id: number) => {
    try { sessionStorage.setItem(SELECTED_GOAL_KEY, String(id)); } catch { /* ignore */ }
    setSelectedGoalIdState(id);
    // Sync profile on goal switch (fire-and-forget)
    if (userId) {
      syncProfileApi(userId, id).catch(() => {});
    }
  }, [userId]);

  const updateGoal = useCallback((goalId: number, updatedGoal: GoalAggregate) => {
    setGoals((prev) => prev.map((g) => (g.id === goalId ? updatedGoal : g)));
  }, []);

  return (
    <GoalsContext.Provider value={{ goals, selectedGoalId, setSelectedGoalId, refreshGoals, updateGoal, isLoading }}>
      {children}
    </GoalsContext.Provider>
  );
}

export function useGoalsContext(): GoalsContextValue {
  const ctx = useContext(GoalsContext);
  if (!ctx) throw new Error('useGoalsContext must be used within GoalsProvider');
  return ctx;
}
