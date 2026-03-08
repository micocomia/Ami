/**
 * Profile endpoints: getProfile, putProfile, syncProfile, autoUpdateProfile
 * Pattern: Types → Api functions → React Query hooks
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../client';
import type {
  ProfileGetResponse,
  ProfilePutRequest,
  SyncProfileResponse,
  AutoProfileUpdateRequest,
  AutoProfileUpdateResponse,
} from '@/types';

// ----- Types -----
export type {
  ProfileGetResponse,
  ProfilePutRequest,
  SyncProfileResponse,
  AutoProfileUpdateRequest,
  AutoProfileUpdateResponse,
};

// ----- Query keys -----
export function profileKeys(userId: string | undefined, goalId?: number) {
  return ['profile', userId, goalId] as const;
}

// ----- API functions -----
export async function getProfileApi(
  userId: string,
  goalId?: number
): Promise<ProfileGetResponse> {
  const params = goalId != null ? { goal_id: goalId } : {};
  const { data } = await apiClient.get<ProfileGetResponse>(`profile/${userId}`, {
    params,
  });
  return data;
}

export async function putProfileApi(
  userId: string,
  goalId: number,
  body: ProfilePutRequest
): Promise<{ ok: boolean }> {
  const { data } = await apiClient.put<{ ok: boolean }>(
    `profile/${userId}/${goalId}`,
    body
  );
  return data;
}

export async function syncProfileApi(
  userId: string,
  goalId: number
): Promise<SyncProfileResponse> {
  const { data } = await apiClient.post<SyncProfileResponse>(
    `sync-profile/${userId}/${goalId}`
  );
  return data;
}

export async function autoUpdateProfileApi(
  body: AutoProfileUpdateRequest
): Promise<AutoProfileUpdateResponse> {
  const { data } = await apiClient.post<AutoProfileUpdateResponse>(
    'profile/auto-update',
    body
  );
  return data;
}

// ----- React Query hooks -----
export function useProfile(userId: string | undefined, goalId?: number, enabled = true) {
  return useQuery({
    queryKey: profileKeys(userId, goalId),
    queryFn: () => getProfileApi(userId!, goalId),
    enabled: Boolean(userId) && enabled,
  });
}

export function usePutProfile(userId: string | undefined, goalId?: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProfilePutRequest) =>
      userId != null && goalId != null
        ? putProfileApi(userId, goalId, body)
        : Promise.reject(new Error('userId and goalId required')),
    onSuccess: (_, body) => {
      if (userId && goalId != null) {
        qc.setQueryData(profileKeys(userId, goalId), (old: ProfileGetResponse | undefined) =>
          old ? { ...old, learner_profile: body.learner_profile } : undefined
        );
      }
    },
  });
}

export function useSyncProfile(userId: string | undefined, goalId?: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      userId != null && goalId != null
        ? syncProfileApi(userId, goalId)
        : Promise.reject(new Error('userId and goalId required')),
    onSuccess: (data) => {
      if (userId && goalId != null) {
        qc.setQueryData(profileKeys(userId, goalId), (old: ProfileGetResponse | undefined) =>
          old ? { ...old, learner_profile: data.learner_profile } : undefined
        );
      }
    },
  });
}

export function useAutoUpdateProfile() {
  return useMutation({
    mutationFn: autoUpdateProfileApi,
  });
}
