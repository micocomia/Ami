/**
 * Bias / fairness audit endpoints (content, chatbot) — mirrors Streamlit request_api helpers.
 */
import { apiClient } from '../client';

export async function auditContentBiasApi(body: {
  generated_content: string;
  learner_information: string;
}): Promise<Record<string, unknown>> {
  const { data } = await apiClient.post<Record<string, unknown>>('audit-content-bias', body);
  return data;
}

export async function auditChatbotBiasApi(body: {
  tutor_responses: string;
  learner_information: string;
}): Promise<Record<string, unknown>> {
  const { data } = await apiClient.post<Record<string, unknown>>('audit-chatbot-bias', body);
  return data;
}
