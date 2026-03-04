/**
 * User state endpoints: getUserState, putUserState, deleteUserState
 * Pattern: Types → Api functions → React Query hooks
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { UserStateResponse, UserState } from '@/types';

// ----- Types -----
export type { UserStateResponse, UserState };

// ----- Query keys -----
export function userStateKeys(userId: string | undefined) {
  return ['userState', userId] as const;
}

// ----- API functions -----
export async function getUserStateApi(userId: string): Promise<UserStateResponse> {
  const { data } = await apiClient.get<UserStateResponse>(`user-state/${userId}`);
  return data;
}

export async function putUserStateApi(
  userId: string,
  state: UserState
): Promise<{ ok: boolean }> {
  const { data } = await apiClient.put<{ ok: boolean }>(`user-state/${userId}`, {
    state,
  });
  return data;
}

export async function deleteUserStateApi(userId: string): Promise<{ ok: boolean }> {
  const { data } = await apiClient.delete<{ ok: boolean }>(`user-state/${userId}`);
  return data;
}

// ----- React Query hooks -----
export function useUserState(userId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: userStateKeys(userId),
    queryFn: () => getUserStateApi(userId!),
    enabled: Boolean(userId) && enabled,
  });
}

export function usePutUserState(userId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (state: UserState) =>
      userId ? putUserStateApi(userId, state) : Promise.reject(new Error('userId required')),
    onSuccess: (_, state) => {
      if (userId) qc.setQueryData(userStateKeys(userId), { state });
    },
  });
}

export function useDeleteUserState(userId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      userId ? deleteUserStateApi(userId) : Promise.reject(new Error('userId required')),
    onSuccess: () => {
      if (userId) qc.removeQueries({ queryKey: userStateKeys(userId) });
    },
  });
}
