/**
 * Config endpoints: appConfig, personas
 * Pattern: Types (re-export) → Api functions → React Query hooks
 */
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { AppConfig, PersonasResponse } from '@/types';

// ----- Types -----
export type { AppConfig, PersonasResponse };

// ----- Query keys -----
export const configKeys = {
  all: ['config'] as const,
  app: ['config', 'app'] as const,
  personas: ['config', 'personas'] as const,
};

// ----- API functions -----
export async function appConfigApi(): Promise<AppConfig> {
  const { data } = await apiClient.get<AppConfig>('config');
  return data;
}

export async function personasApi(): Promise<PersonasResponse> {
  const { data } = await apiClient.get<PersonasResponse>('personas');
  return data;
}

// ----- React Query hooks -----
export function useAppConfig() {
  return useQuery({
    queryKey: configKeys.app,
    queryFn: appConfigApi,
  });
}

export function usePersonas() {
  return useQuery({
    queryKey: configKeys.personas,
    queryFn: personasApi,
  });
}
