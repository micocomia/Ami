/**
 * Metrics endpoints: getBehavioralMetrics, getQuizMix, getSessionMasteryStatus
 * Pattern: Types → Api functions → React Query hooks
 */
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../client';
import type {
  BehavioralMetricsResponse,
  QuizMixResponse,
  SessionMasteryStatusResponse,
} from '@/types';

// ----- Types -----
export type {
  BehavioralMetricsResponse,
  QuizMixResponse,
  SessionMasteryStatusResponse,
};

// ----- Query keys -----
export function behavioralMetricsKeys(userId: string | undefined, goalId?: number) {
  return ['behavioralMetrics', userId, goalId] as const;
}

export function quizMixKeys(
  userId: string | undefined,
  goalId?: number,
  sessionIndex?: number
) {
  return ['quizMix', userId, goalId, sessionIndex] as const;
}

export function sessionMasteryKeys(userId: string | undefined, goalId?: number) {
  return ['sessionMastery', userId, goalId] as const;
}

// ----- API functions -----
export async function getBehavioralMetricsApi(
  userId: string,
  goalId?: number
): Promise<BehavioralMetricsResponse> {
  const params = goalId != null ? { goal_id: goalId } : {};
  const { data } = await apiClient.get<BehavioralMetricsResponse>(
    `behavioral-metrics/${userId}`,
    { params }
  );
  return data;
}

export async function getQuizMixApi(
  userId: string,
  goalId: number,
  sessionIndex: number
): Promise<QuizMixResponse> {
  const { data } = await apiClient.get<QuizMixResponse>(`quiz-mix/${userId}`, {
    params: { goal_id: goalId, session_index: sessionIndex },
  });
  return data;
}

export async function getSessionMasteryStatusApi(
  userId: string,
  goalId: number
): Promise<SessionMasteryStatusResponse> {
  const { data } = await apiClient.get<SessionMasteryStatusResponse>(
    `session-mastery-status/${userId}`,
    { params: { goal_id: goalId } }
  );
  return data;
}

// ----- React Query hooks -----
export function useBehavioralMetrics(
  userId: string | undefined,
  goalId?: number,
  enabled = true
) {
  return useQuery({
    queryKey: behavioralMetricsKeys(userId, goalId),
    queryFn: () => getBehavioralMetricsApi(userId!, goalId),
    enabled: Boolean(userId) && enabled,
  });
}

export function useQuizMix(
  userId: string | undefined,
  goalId: number | undefined,
  sessionIndex: number | undefined,
  enabled = true
) {
  return useQuery({
    queryKey: quizMixKeys(userId, goalId, sessionIndex),
    queryFn: () => getQuizMixApi(userId!, goalId!, sessionIndex!),
    enabled:
      Boolean(userId) && goalId != null && sessionIndex != null && enabled,
  });
}

export function useSessionMasteryStatus(
  userId: string | undefined,
  goalId: number | undefined,
  enabled = true
) {
  return useQuery({
    queryKey: sessionMasteryKeys(userId, goalId),
    queryFn: () => getSessionMasteryStatusApi(userId!, goalId!),
    enabled: Boolean(userId) && goalId != null && enabled,
  });
}
