/**
 * Auth endpoints: register, login, me, deleteUser
 * Pattern: Types (re-export) → Api functions → React Query hooks
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../client';
import type {
  AuthRegisterRequest,
  AuthLoginRequest,
  AuthTokenResponse,
  AuthMeResponse,
} from '@/types';

const AUTH_TOKEN_KEY = 'auth_token';

function saveToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

// ----- Types -----
export type { AuthRegisterRequest, AuthLoginRequest, AuthTokenResponse, AuthMeResponse };

// ----- Query keys -----
export const authKeys = {
  all: ['auth'] as const,
  me: ['auth', 'me'] as const,
};

// ----- API functions -----
export async function authMeApi(): Promise<AuthMeResponse> {
  const { data } = await apiClient.get<AuthMeResponse>('auth/me');
  return data;
}

export async function registerApi(body: AuthRegisterRequest): Promise<AuthTokenResponse> {
  const { data } = await apiClient.post<AuthTokenResponse>('auth/register', body);
  return data;
}

export async function loginApi(body: AuthLoginRequest): Promise<AuthTokenResponse> {
  const { data } = await apiClient.post<AuthTokenResponse>('auth/login', body);
  return data;
}

export async function deleteUserApi(): Promise<{ ok: boolean }> {
  const { data } = await apiClient.delete<{ ok: boolean }>('auth/user');
  return data;
}

// ----- React Query hooks -----
export function useAuthMe(enabled = true) {
  return useQuery({
    queryKey: authKeys.me,
    queryFn: authMeApi,
    enabled,
  });
}

export function useRegister() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: registerApi,
    onSuccess: (data) => {
      saveToken(data.token);
      qc.setQueryData(authKeys.me, { username: data.username });
    },
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: loginApi,
    onSuccess: (data) => {
      saveToken(data.token);
      qc.setQueryData(authKeys.me, { username: data.username });
    },
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteUserApi,
    onSuccess: () => {
      localStorage.removeItem(AUTH_TOKEN_KEY);
      qc.removeQueries({ queryKey: authKeys.me });
    },
  });
}
