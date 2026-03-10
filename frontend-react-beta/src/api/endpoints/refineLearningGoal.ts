/**
 * POST /refine-learning-goal
 * Types, optional Zod schema, api function, and React Query hook.
 */
import { z } from 'zod';
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../client';
import type {
  RefineLearningGoalRequest,
  RefineLearningGoalResponse,
} from '@/types';

// ----- Types (re-export for convenience) -----
export type { RefineLearningGoalRequest, RefineLearningGoalResponse };

// ----- Zod schema (optional runtime validation) -----
export const refineLearningGoalRequestSchema: z.ZodType<RefineLearningGoalRequest> =
  z.object({
    learning_goal: z.string().min(1, 'Learning goal is required'),
    learner_information: z.string().optional().default(''),
    model_provider: z.string().optional(),
    model_name: z.string().optional(),
    method_name: z.string().optional().default('genmentor'),
  });

export const refineLearningGoalResponseSchema = z.union([
  z.string(),
  z.object({ refined_goal: z.string().optional() }).passthrough(),
]);

// ----- API function -----
export async function refineLearningGoalApi(
  req: RefineLearningGoalRequest
): Promise<RefineLearningGoalResponse> {
  const { data } = await apiClient.post<RefineLearningGoalResponse>(
    'refine-learning-goal',
    req
  );
  return data;
}

// ----- Query keys -----
export const refineLearningGoalKeys = {
  all: ['refineLearningGoal'] as const,
};

// ----- React Query hook -----
export function useRefineLearningGoal() {
  return useMutation({
    mutationKey: refineLearningGoalKeys.all,
    mutationFn: refineLearningGoalApi,
  });
}
