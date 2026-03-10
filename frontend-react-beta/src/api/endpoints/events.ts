/**
 * Events endpoints: logEvent, getEvents
 * Pattern: Types → Api functions → React Query hooks
 */
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { BehaviorEventRequest, LogEventResponse, GetEventsResponse } from '@/types';

// ----- Types -----
export type { BehaviorEventRequest, LogEventResponse, GetEventsResponse };

// ----- Query keys -----
export function eventsKeys(userId: string | undefined) {
  return ['events', userId] as const;
}

// ----- API functions -----
export async function logEventApi(
  body: BehaviorEventRequest
): Promise<LogEventResponse> {
  const { data } = await apiClient.post<LogEventResponse>('events/log', body);
  return data;
}

export async function getEventsApi(userId: string): Promise<GetEventsResponse> {
  const { data } = await apiClient.get<GetEventsResponse>(`events/${userId}`);
  return data;
}

// ----- React Query hooks -----
export function useLogEvent() {
  return useMutation({
    mutationFn: logEventApi,
  });
}

export function useEvents(userId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: eventsKeys(userId),
    queryFn: () => getEventsApi(userId!),
    enabled: Boolean(userId) && enabled,
  });
}
