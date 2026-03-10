/**
 * Chat with tutor endpoint
 * Pattern: Types → Api function → React Query hook
 */
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { ChatWithTutorRequest, ChatWithTutorResponse } from '@/types';

// ----- Types -----
export type { ChatWithTutorRequest, ChatWithTutorResponse };

// ----- API function -----
export async function chatWithTutorApi(body: ChatWithTutorRequest): Promise<ChatWithTutorResponse> {
  const { data } = await apiClient.post<ChatWithTutorResponse>('chat-with-tutor', body);
  return data;
}

// ----- React Query hook -----
export function useChatWithTutor() {
  return useMutation({ mutationFn: chatWithTutorApi });
}

