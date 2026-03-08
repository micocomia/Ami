import { useGoalsContext } from '@/context/GoalsContext';
import type { GoalAggregate } from '@/types';

export function useActiveGoal(): GoalAggregate | null {
  const { goals, selectedGoalId } = useGoalsContext();
  return goals.find((g) => g.id === selectedGoalId) ?? goals[0] ?? null;
}
