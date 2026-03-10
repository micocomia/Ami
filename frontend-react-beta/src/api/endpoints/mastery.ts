/**
 * Mastery endpoint: evaluateMastery
 * Pattern: Types → Api function → React Query hook
 */
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../client';
import type {
  MasteryEvaluationRequest,
  MasteryEvaluationResponse,
} from '@/types';

// ----- Types -----
export type { MasteryEvaluationRequest, MasteryEvaluationResponse };

// ----- Query keys -----
export const masteryKeys = {
  all: ['mastery'] as const,
};

// ----- API function -----
export async function evaluateMasteryApi(
  body: MasteryEvaluationRequest
): Promise<MasteryEvaluationResponse> {
  const { data } = await apiClient.post<MasteryEvaluationResponse>(
    'evaluate-mastery',
    body
  );
  return data;
}

// ----- React Query hook -----
export function useEvaluateMastery() {
  return useMutation({
    mutationKey: masteryKeys.all,
    mutationFn: evaluateMasteryApi,
  });
}
