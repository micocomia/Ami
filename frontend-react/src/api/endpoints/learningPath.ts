/**
 * Learning path endpoints: schedule, reschedule, scheduleAgentic, adapt
 * Pattern: Types → Api functions → React Query hooks
 */
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../client';
import type {
  ScheduleLearningPathRequest,
  ScheduleLearningPathResponse,
  AgenticLearningPathRequest,
  ScheduleLearningPathAgenticResponse,
  AdaptLearningPathRequest,
  AdaptLearningPathResponse,
} from '@/types';

// ----- Types -----
export type {
  ScheduleLearningPathRequest,
  ScheduleLearningPathResponse,
  AgenticLearningPathRequest,
  ScheduleLearningPathAgenticResponse,
  AdaptLearningPathRequest,
  AdaptLearningPathResponse,
};

// ----- Query keys -----
export const learningPathKeys = {
  all: ['learningPath'] as const,
};

// ----- API functions -----
export async function scheduleLearningPathApi(
  body: ScheduleLearningPathRequest
): Promise<ScheduleLearningPathResponse> {
  const { data } = await apiClient.post<ScheduleLearningPathResponse>(
    'schedule-learning-path',
    body
  );
  return data;
}

export async function scheduleLearningPathAgenticApi(
  body: AgenticLearningPathRequest
): Promise<ScheduleLearningPathAgenticResponse> {
  const { data } = await apiClient.post<ScheduleLearningPathAgenticResponse>(
    'schedule-learning-path-agentic',
    body
  );
  return data;
}

export async function adaptLearningPathApi(
  body: AdaptLearningPathRequest
): Promise<AdaptLearningPathResponse> {
  const { data } = await apiClient.post<AdaptLearningPathResponse>(
    'adapt-learning-path',
    body
  );
  return data;
}

// ----- React Query hooks -----
export function useScheduleLearningPath() {
  return useMutation({
    mutationKey: learningPathKeys.all,
    mutationFn: scheduleLearningPathApi,
  });
}

export function useScheduleLearningPathAgentic() {
  return useMutation({
    mutationKey: learningPathKeys.all,
    mutationFn: scheduleLearningPathAgenticApi,
  });
}

export function useAdaptLearningPath() {
  return useMutation({
    mutationKey: learningPathKeys.all,
    mutationFn: adaptLearningPathApi,
  });
}
