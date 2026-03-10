/**
 * PDF endpoint: extractPdfText
 * Pattern: Types → Api function → React Query hook
 */
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { ExtractPdfTextResponse } from '@/types';

// ----- Types -----
export type { ExtractPdfTextResponse };

// ----- Query keys -----
export const pdfKeys = {
  all: ['pdf'] as const,
};

// ----- API function -----
export async function extractPdfTextApi(
  file: File
): Promise<ExtractPdfTextResponse> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await apiClient.post<ExtractPdfTextResponse>(
    'extract-pdf-text',
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  );
  return data;
}

// ----- React Query hook -----
export function useExtractPdfText() {
  return useMutation({
    mutationKey: pdfKeys.all,
    mutationFn: extractPdfTextApi,
  });
}
