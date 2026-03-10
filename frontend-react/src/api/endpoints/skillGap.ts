/**
 * Skill gap endpoints: identifySkillGap, auditBias, createProfile, validateFairness
 * Pattern: Types → Api functions → React Query hooks (all mutations)
 *
 * This mirrors `frontend-react/src/api/endpoints/skillGap.ts` to ensure
 * request/response contracts stay aligned with the existing backend.
 */
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../client';
import type {
  SkillGapIdentificationRequest,
  IdentifySkillGapResponse,
  BiasAuditRequest,
  CreateLearnerProfileRequest,
  CreateLearnerProfileResponse,
  ValidateProfileFairnessRequest,
  LearnerProfileResponse,
} from '@/types';

const LONG_LLM_TIMEOUT_MS = 300_000;

// ----- Types -----
export type {
  SkillGapIdentificationRequest,
  IdentifySkillGapResponse,
  BiasAuditRequest,
  CreateLearnerProfileRequest,
  CreateLearnerProfileResponse,
  ValidateProfileFairnessRequest,
  LearnerProfileResponse,
};

// ----- API functions -----
export async function identifySkillGapApi(
  body: SkillGapIdentificationRequest,
): Promise<IdentifySkillGapResponse> {
  const { data } = await apiClient.post<IdentifySkillGapResponse>(
    'identify-skill-gap-with-info',
    body,
    {
      timeout: LONG_LLM_TIMEOUT_MS,
    },
  );
  return data;
}

export async function auditSkillGapBiasApi(body: BiasAuditRequest): Promise<Record<string, unknown>> {
  const { data } = await apiClient.post<Record<string, unknown>>('audit-skill-gap-bias', body, {
    timeout: LONG_LLM_TIMEOUT_MS,
  });
  return data;
}

export async function createLearnerProfileWithInfoApi(
  body: CreateLearnerProfileRequest,
): Promise<CreateLearnerProfileResponse> {
  const { data } = await apiClient.post<CreateLearnerProfileResponse>(
    'create-learner-profile-with-info',
    body,
    {
      timeout: LONG_LLM_TIMEOUT_MS,
    },
  );
  return data;
}

export async function validateProfileFairnessApi(
  body: ValidateProfileFairnessRequest,
): Promise<Record<string, unknown>> {
  const { data } = await apiClient.post<Record<string, unknown>>('validate-profile-fairness', body, {
    timeout: LONG_LLM_TIMEOUT_MS,
  });
  return data;
}

// ----- React Query hooks -----
export function useIdentifySkillGap() {
  return useMutation({ mutationFn: identifySkillGapApi });
}

export function useAuditSkillGapBias() {
  return useMutation({ mutationFn: auditSkillGapBiasApi });
}

export function useCreateLearnerProfileWithInfo() {
  return useMutation({ mutationFn: createLearnerProfileWithInfoApi });
}

export function useValidateProfileFairness() {
  return useMutation({ mutationFn: validateProfileFairnessApi });
}

