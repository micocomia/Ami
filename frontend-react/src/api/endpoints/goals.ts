/**
 * Goals endpoints: list, create, patch, delete, getRuntimeState
 * Pattern: Types → Api functions → React Query hooks
 *
 * This mirrors the proven implementation in `frontend-react/src/api/endpoints/goals.ts`,
 * but uses the shared types from `@/types` and the beta axios client.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../client';
import type {
  GoalAggregate,
  GoalsListResponse,
  GoalCreateRequest,
  GoalUpdateRequest,
  GoalRuntimeState,
} from '@/types';

// ----- Types -----
export type { GoalAggregate, GoalsListResponse, GoalCreateRequest, GoalUpdateRequest, GoalRuntimeState };

// ----- Query keys -----
export const goalsKeys = {
  all: ['goals'] as const,
  list: (userId: string) => ['goals', userId] as const,
  runtimeState: (userId: string, goalId: number) => ['goalRuntimeState', userId, goalId] as const,
};

// ----- API functions -----
export async function listGoalsApi(userId: string): Promise<GoalsListResponse> {
  const { data } = await apiClient.get<GoalsListResponse>(`goals/${userId}`);
  return data;
}

export async function createGoalApi(userId: string, body: GoalCreateRequest): Promise<GoalAggregate> {
  const { data } = await apiClient.post<GoalAggregate>(`goals/${userId}`, body);
  return data;
}

export async function patchGoalApi(
  userId: string,
  goalId: number,
  body: GoalUpdateRequest,
): Promise<GoalAggregate> {
  const { data } = await apiClient.patch<GoalAggregate>(`goals/${userId}/${goalId}`, body);
  return data;
}

export async function deleteGoalApi(userId: string, goalId: number): Promise<{ ok: boolean }> {
  const { data } = await apiClient.delete<{ ok: boolean }>(`goals/${userId}/${goalId}`);
  return data;
}

export async function getGoalRuntimeStateApi(userId: string, goalId: number): Promise<GoalRuntimeState> {
  const { data } = await apiClient.get<GoalRuntimeState>(`goal-runtime-state/${userId}`, {
    params: { goal_id: goalId },
  });
  return data;
}

// ----- React Query hooks -----
export function useGoals(userId: string | undefined) {
  return useQuery({
    queryKey: userId ? goalsKeys.list(userId) : ['goals', null],
    queryFn: () => listGoalsApi(userId!),
    enabled: Boolean(userId),
  });
}

export function useCreateGoal(userId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: GoalCreateRequest) =>
      userId ? createGoalApi(userId, body) : Promise.reject(new Error('userId required')),
    onSuccess: () => {
      if (userId) qc.invalidateQueries({ queryKey: goalsKeys.list(userId) });
    },
  });
}

export function usePatchGoal(userId: string | undefined, goalId: number | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: GoalUpdateRequest) =>
      userId != null && goalId != null
        ? patchGoalApi(userId, goalId, body)
        : Promise.reject(new Error('userId and goalId required')),
    onSuccess: () => {
      if (userId) qc.invalidateQueries({ queryKey: goalsKeys.list(userId) });
    },
  });
}

export function useDeleteGoal(userId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (goalId: number) =>
      userId ? deleteGoalApi(userId, goalId) : Promise.reject(new Error('userId required')),
    onSuccess: () => {
      if (userId) qc.invalidateQueries({ queryKey: goalsKeys.list(userId) });
    },
  });
}

export function useGoalRuntimeState(userId: string | undefined, goalId: number | undefined) {
  return useQuery({
    queryKey: userId && goalId != null ? goalsKeys.runtimeState(userId, goalId) : ['goalRuntimeState', null],
    queryFn: () => getGoalRuntimeStateApi(userId!, goalId!),
    enabled: Boolean(userId) && goalId != null,
    refetchOnWindowFocus: false,
  });
}

