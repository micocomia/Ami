/**
 * Content, session, dashboard, and profile-update endpoints
 * Pattern: Types → Api functions → React Query hooks
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../client';
import type {
  LearningContentResponse,
  GenerateLearningContentRequest,
  SessionActivityRequest,
  SessionActivityResponse,
  CompleteSessionRequest,
  CompleteSessionResponse,
  SubmitContentFeedbackRequest,
  SubmitContentFeedbackResponse,
  DashboardMetricsResponse,
  LearnerProfileResponse,
  LearningPreferencesUpdateRequest,
  LearnerInformationUpdateRequest,
} from '@/types';

// ----- Types -----
export type {
  LearningContentResponse,
  GenerateLearningContentRequest,
  SessionActivityRequest,
  SessionActivityResponse,
  CompleteSessionRequest,
  CompleteSessionResponse,
  SubmitContentFeedbackRequest,
  SubmitContentFeedbackResponse,
  DashboardMetricsResponse,
};

// ----- Query keys -----
export const contentKeys = {
  session: (userId: string, goalId: number, sessionIndex: number) =>
    ['learningContent', userId, goalId, sessionIndex] as const,
  dashboardMetrics: (userId: string, goalId?: number) =>
    ['dashboardMetrics', userId, goalId] as const,
};

// ----- API functions -----

/** GET /learning-content — 404 resolves (not rejects) so callers can detect cache miss */
export async function getLearningContentApi(
  userId: string,
  goalId: number,
  sessionIndex: number
): Promise<{ status: number; data: LearningContentResponse | null }> {
  const response = await apiClient.get<LearningContentResponse>(
    `learning-content/${userId}/${goalId}/${sessionIndex}`,
    { validateStatus: (s) => s < 500 }
  );
  return { status: response.status, data: response.status === 200 ? response.data : null };
}

export async function generateLearningContentApi(body: GenerateLearningContentRequest): Promise<LearningContentResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 300_000);
  try {
    const { data } = await apiClient.post<LearningContentResponse>('generate-learning-content', body, {
      signal: controller.signal,
    });
    return data;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function deleteLearningContentApi(userId: string, goalId: number, sessionIndex: number): Promise<void> {
  await apiClient.delete(`learning-content/${userId}/${goalId}/${sessionIndex}`);
}

export async function sessionActivityApi(body: SessionActivityRequest): Promise<SessionActivityResponse> {
  const { data } = await apiClient.post<SessionActivityResponse>('session-activity', body);
  return data;
}

export async function completeSessionApi(body: CompleteSessionRequest): Promise<CompleteSessionResponse> {
  const { data } = await apiClient.post<CompleteSessionResponse>('complete-session', body);
  return data;
}

export async function submitContentFeedbackApi(body: SubmitContentFeedbackRequest): Promise<SubmitContentFeedbackResponse> {
  const { data } = await apiClient.post<SubmitContentFeedbackResponse>('submit-content-feedback', body);
  return data;
}

export async function getDashboardMetricsApi(userId: string, goalId?: number): Promise<DashboardMetricsResponse> {
  const { data } = await apiClient.get<DashboardMetricsResponse>(`dashboard-metrics/${userId}`, {
    params: goalId != null ? { goal_id: goalId } : {},
  });
  return data;
}

export async function updateLearningPreferencesApi(body: LearningPreferencesUpdateRequest): Promise<LearnerProfileResponse> {
  const { data } = await apiClient.post<LearnerProfileResponse>('update-learning-preferences', body);
  return data;
}

export async function updateLearnerInformationApi(body: LearnerInformationUpdateRequest): Promise<LearnerProfileResponse> {
  const { data } = await apiClient.post<LearnerProfileResponse>('update-learner-information', body);
  return data;
}

export async function deleteUserDataApi(userId: string): Promise<{ ok: boolean }> {
  const { data } = await apiClient.delete<{ ok: boolean }>(`user-data/${userId}`);
  return data;
}

// ----- React Query hooks -----

export function useGetLearningContent(
  userId: string | undefined,
  goalId: number | undefined,
  sessionIndex: number | undefined
) {
  const enabled = Boolean(userId) && goalId != null && sessionIndex != null;
  return useQuery({
    queryKey: enabled ? contentKeys.session(userId!, goalId!, sessionIndex!) : ['learningContent', null],
    queryFn: () => getLearningContentApi(userId!, goalId!, sessionIndex!),
    enabled,
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function useGenerateLearningContent() {
  return useMutation({ mutationFn: generateLearningContentApi });
}

export function useDeleteLearningContent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, goalId, sessionIndex }: { userId: string; goalId: number; sessionIndex: number }) =>
      deleteLearningContentApi(userId, goalId, sessionIndex),
    onSuccess: (_, { userId, goalId, sessionIndex }) => {
      qc.invalidateQueries({ queryKey: contentKeys.session(userId, goalId, sessionIndex) });
    },
  });
}

export function useSessionActivity() {
  return useMutation({ mutationFn: sessionActivityApi });
}

export function useCompleteSession() {
  return useMutation({ mutationFn: completeSessionApi });
}

export function useSubmitContentFeedback() {
  return useMutation({ mutationFn: submitContentFeedbackApi });
}

export function useDashboardMetrics(userId: string | undefined, goalId?: number) {
  return useQuery({
    queryKey: userId ? contentKeys.dashboardMetrics(userId, goalId) : ['dashboardMetrics', null],
    queryFn: () => getDashboardMetricsApi(userId!, goalId),
    enabled: Boolean(userId),
    staleTime: 60_000,
  });
}

export function useUpdateLearningPreferences() {
  return useMutation({ mutationFn: updateLearningPreferencesApi });
}

export function useUpdateLearnerInformation() {
  return useMutation({ mutationFn: updateLearnerInformationApi });
}

export function useDeleteUserData() {
  return useMutation({ mutationFn: (userId: string) => deleteUserDataApi(userId) });
}
