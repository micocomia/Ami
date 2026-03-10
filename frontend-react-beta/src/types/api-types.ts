/**
 * API request/response TypeScript types (aligned with API_CONTRACT.md)
 */

export interface BaseRequest {
  model_provider?: string;
  model_name?: string;
  method_name?: string;
}

export interface ApiErrorBody {
  detail: string;
}

export interface AuthRegisterRequest {
  username: string;
  password: string;
}

export interface AuthLoginRequest {
  username: string;
  password: string;
}

export interface AuthTokenResponse {
  token: string;
  username: string;
}

export interface AuthMeResponse {
  username: string;
}

export interface QuizMix {
  single_choice_count: number;
  multiple_choice_count: number;
  true_false_count: number;
  short_answer_count: number;
  open_ended_count: number;
}

export interface FslsmDimensionConfig {
  low_threshold: number;
  high_threshold: number;
  low_label: string;
  high_label: string;
  neutral_label: string;
}

export interface AppConfig {
  skill_levels: string[];
  default_session_count: number;
  default_llm_type: string;
  default_method_name: string;
  motivational_trigger_interval_secs: number;
  max_refinement_iterations: number;
  mastery_threshold_default?: number;
  mastery_threshold_by_proficiency?: Record<string, number>;
  quiz_mix_by_proficiency?: Record<string, QuizMix>;
  fslsm_thresholds?: Record<string, FslsmDimensionConfig>;
  fslsm_activation_threshold?: number;
  [key: string]: unknown;
}

export interface PersonaInfo {
  description: string;
  fslsm_dimensions: Record<string, number>;
}

export interface PersonasResponse {
  personas: Record<string, PersonaInfo>;
}

export interface LlmModelItem {
  model_name: string;
  model_provider: string;
}

export interface ListLlmModelsResponse {
  models: LlmModelItem[];
}

export interface SessionLearningTime {
  start_time?: number;
  end_time?: number;
  trigger_time_list?: number[];
}

export interface QuizQuestionBase {
  question: string;
  [key: string]: unknown;
}

export interface DocumentQuiz {
  single_choice_questions?: Array<QuizQuestionBase & { options: string[]; correct_answer: string | number }>;
  multiple_choice_questions?: Array<QuizQuestionBase & { options: string[]; correct_answers: (string | number)[] }>;
  true_false_questions?: Array<QuizQuestionBase & { correct_answer: boolean }>;
  short_answer_questions?: Array<QuizQuestionBase & { expected_answer: string }>;
  open_ended_questions?: Array<QuizQuestionBase & { rubric: string; example_answer: string }>;
}

export interface DocumentCache {
  quizzes?: DocumentQuiz;
  learning_document?: string | Record<string, unknown>;
  [key: string]: unknown;
}

export interface LearnerProfile {
  learning_goal?: string;
  cognitive_status?: Record<string, unknown>;
  learning_preferences?: { fslsm_dimensions?: Record<string, number>; [key: string]: unknown };
  behavioral_patterns?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface LearningPathSession {
  id: string;
  if_learned?: boolean;
  mastery_score?: number;
  is_mastered?: boolean;
  mastery_threshold?: number;
  [key: string]: unknown;
}

export interface GoalInState {
  id: number;
  learning_path?: LearningPathSession[];
  learner_profile?: LearnerProfile;
  [key: string]: unknown;
}

export interface UserState {
  goals?: GoalInState[];
  session_learning_times?: Record<string, SessionLearningTime>;
  learned_skills_history?: Record<string, number[]>;
  document_caches?: Record<string, DocumentCache>;
  [key: string]: unknown;
}

export interface UserStateResponse {
  state: UserState;
}

export interface UserStatePutRequest {
  state: UserState;
}

export interface BehaviorEventRequest {
  user_id: string;
  event_type: string;
  payload?: Record<string, unknown>;
  ts?: string;
}

export interface LogEventResponse {
  ok: boolean;
  event_count: number;
}

export interface ProfileGetResponse {
  user_id: string;
  goal_id?: number;
  learner_profile?: LearnerProfile;
  profiles?: Array<{ goal_id: number; learner_profile: LearnerProfile }>;
}

export interface ProfilePutRequest {
  learner_profile: LearnerProfile;
}

export interface SyncProfileResponse {
  learner_profile: LearnerProfile;
}

export interface AutoProfileUpdateRequest {
  user_id: string;
  goal_id?: number;
  model_provider?: string;
  model_name?: string;
  learning_goal?: string;
  learner_information?: string | Record<string, unknown>;
  skill_gaps?: string | Record<string, unknown>;
  session_information?: Record<string, unknown>;
}

export interface AutoProfileUpdateResponse {
  ok: boolean;
  mode: 'initialized' | 'updated';
  user_id: string;
  goal_id: number;
  event_count_used: number;
  learner_profile: LearnerProfile;
}

export interface BehavioralMetricsResponse {
  user_id: string;
  goal_id: number | null;
  sessions_completed: number;
  total_sessions_in_path: number;
  sessions_learned: number;
  avg_session_duration_sec: number;
  total_learning_time_sec: number;
  motivational_triggers_count: number;
  mastery_history: number[];
  latest_mastery_rate: number | null;
}

export type QuizMixResponse = QuizMix;

export interface SessionMasteryItem {
  session_id: string;
  is_mastered: boolean;
  mastery_score: number | null;
  mastery_threshold: number;
  if_learned: boolean;
}

export type SessionMasteryStatusResponse = SessionMasteryItem[];

export interface QuizAnswersPayload {
  single_choice_questions?: (string | number)[];
  multiple_choice_questions?: (string | number)[][];
  true_false_questions?: boolean[];
  short_answer_questions?: (string | null)[];
  open_ended_questions?: (string | null)[];
}

export interface MasteryEvaluationRequest {
  user_id: string;
  goal_id: number;
  session_index: number;
  quiz_answers: QuizAnswersPayload;
}

export interface ShortAnswerFeedbackItem {
  is_correct: boolean;
  feedback: string;
}

export interface OpenEndedFeedbackItem {
  solo_level: string;
  score: number;
  feedback: string;
}

export interface MasteryEvaluationResponse {
  score_percentage: number;
  is_mastered: boolean;
  threshold: number;
  correct_count: number;
  total_count: number;
  session_id: string;
  plan_adaptation_suggested: boolean;
  short_answer_feedback?: ShortAnswerFeedbackItem[];
  open_ended_feedback?: OpenEndedFeedbackItem[];
}

export interface RefineLearningGoalRequest extends BaseRequest {
  learning_goal: string;
  learner_information?: string;
}

/** Backend may return refined goal as string or object */
export type RefineLearningGoalResponse = string | { refined_goal?: string; [key: string]: unknown };

export interface SkillGapIdentificationRequest extends BaseRequest {
  learning_goal: string;
  learner_information: string;
  skill_requirements?: string;
  user_id?: string;
  goal_id?: number;
}

export interface IdentifySkillGapResponse {
  skill_gaps?: Record<string, unknown>;
  goal_assessment?: unknown;
  retrieved_sources?: unknown[];
  [key: string]: unknown;
}

export interface BiasAuditRequest extends BaseRequest {
  skill_gaps: string;
  learner_information: string;
}

export interface CreateLearnerProfileRequest extends BaseRequest {
  learning_goal: string;
  learner_information: string;
  skill_gaps: string;
  user_id?: string;
  goal_id?: number;
}

export interface CreateLearnerProfileResponse {
  learner_profile: LearnerProfile;
}

export interface ValidateProfileFairnessRequest extends BaseRequest {
  learner_profile: string;
  learner_information: string;
  persona_name?: string;
}

export interface UpdateLearnerProfileRequest extends BaseRequest {
  learner_profile: string;
  learner_interactions: string;
  learner_information?: string;
  session_information?: string;
  user_id?: string;
  goal_id?: number;
}

export interface CognitiveStatusUpdateRequest extends BaseRequest {
  learner_profile: string;
  session_information: string;
  user_id?: string;
  goal_id?: number;
}

export interface LearningPreferencesUpdateRequest extends BaseRequest {
  learner_profile: string;
  learner_interactions: string;
  learner_information?: string;
  user_id?: string;
  goal_id?: number;
}

export interface LearnerProfileResponse {
  learner_profile: LearnerProfile;
}

export interface ScheduleLearningPathRequest extends BaseRequest {
  learner_profile: string;
  session_count: number;
}

export interface ScheduleLearningPathResponse {
  learning_path: LearningPathSession[];
  retrieved_sources?: unknown[];
}

export interface RescheduleLearningPathRequest extends BaseRequest {
  learner_profile: string;
  learning_path: string;
  session_count?: number;
  other_feedback?: string;
}

export interface RescheduleLearningPathResponse {
  rescheduled_learning_path?: LearningPathSession[];
  learning_path?: LearningPathSession[];
  [key: string]: unknown;
}

export interface AgenticLearningPathRequest extends BaseRequest {
  learner_profile: string;
  session_count?: number;
}

export interface AgentMetadata {
  decision?: Record<string, unknown>;
  fslsm_deltas?: Record<string, unknown>;
  mastery_results?: unknown[];
  evaluation_feedback?: unknown;
  evaluation?: unknown;
  [key: string]: unknown;
}

export interface ScheduleLearningPathAgenticResponse {
  learning_path: LearningPathSession[];
  agent_metadata?: AgentMetadata;
}

export interface AdaptLearningPathRequest extends BaseRequest {
  user_id: string;
  goal_id: number;
  new_learner_profile: string;
}

export interface AdaptLearningPathResponse {
  learning_path: LearningPathSession[];
  agent_metadata?: AgentMetadata;
}

export interface ExploreKnowledgePointsRequest {
  learner_profile: string;
  learning_path: string;
  learning_session: string;
}

export interface DraftKnowledgePointRequest extends BaseRequest {
  learner_profile: string;
  learning_path: string;
  learning_session: string;
  knowledge_points: string;
  knowledge_point: string;
  use_search: boolean;
}

export interface DraftKnowledgePointResponse {
  knowledge_draft: string;
}

export interface DraftKnowledgePointsRequest extends BaseRequest {
  learner_profile: string;
  learning_path: string;
  learning_session: string;
  knowledge_points: string;
  allow_parallel: boolean;
  use_search: boolean;
}

export interface DraftKnowledgePointsResponse {
  knowledge_drafts: unknown[];
}

export interface IntegrateLearningDocumentRequest extends BaseRequest {
  learner_profile: string;
  learning_path: string;
  learning_session: string;
  knowledge_points: string;
  knowledge_drafts: string;
  output_markdown?: boolean;
}

export interface IntegrateLearningDocumentResponse {
  learning_document: string | Record<string, unknown>;
  content_format: 'standard' | 'visual_enhanced' | 'podcast';
  audio_url: string | null;
  document_is_markdown: boolean;
}

export interface GenerateDocumentQuizzesRequest {
  learner_profile: string;
  learning_document: string;
  single_choice_count?: number;
  multiple_choice_count?: number;
  true_false_count?: number;
  short_answer_count?: number;
  open_ended_count?: number;
}

export interface GenerateDocumentQuizzesResponse {
  document_quiz: DocumentQuiz;
}

export interface TailorKnowledgeContentRequest extends BaseRequest {
  learner_profile: string;
  learning_path: string;
  learning_session: string;
  use_search?: boolean;
  allow_parallel?: boolean;
  with_quiz?: boolean;
}

export interface TailorKnowledgeContentResponse {
  tailored_content: Record<string, unknown>;
}

export interface SimulateContentFeedbackRequest extends BaseRequest {
  learner_profile: string;
  learning_content: string;
}

export interface SimulateContentFeedbackResponse {
  feedback: Record<string, unknown>;
}

export interface ChatWithTutorRequest extends BaseRequest {
  messages: string;
  learner_profile: string;
}

export interface ChatWithTutorResponse {
  response: string;
}

export interface ExtractPdfTextResponse {
  text: string;
}

export interface GetEventsResponse {
  user_id: string;
  events: unknown[];
}

// ─── Goals ───────────────────────────────────────────────────────────────────

export interface GoalAggregate {
  id: number;
  learning_goal: string;
  skill_gaps?: Record<string, unknown>;
  goal_assessment?: unknown;
  goal_context?: unknown;
  retrieved_sources?: unknown[];
  bias_audit?: unknown;
  profile_fairness?: unknown;
  learning_path?: LearningPathSession[];
  plan_agent_metadata?: AgentMetadata;
  learner_profile?: LearnerProfile;
  is_completed?: boolean;
  is_deleted?: boolean;
  [key: string]: unknown;
}

export interface GoalsListResponse {
  goals: GoalAggregate[];
}

export interface GoalCreateRequest {
  learning_goal: string;
  skill_gaps?: unknown;
  goal_assessment?: unknown;
  goal_context?: unknown;
  retrieved_sources?: unknown[];
  bias_audit?: unknown;
  profile_fairness?: unknown;
  learner_profile?: LearnerProfile;
  learning_path?: LearningPathSession[];
  plan_agent_metadata?: AgentMetadata;
}

export interface GoalUpdateRequest {
  learning_goal?: string;
  learning_path?: LearningPathSession[];
  plan_agent_metadata?: AgentMetadata;
  [key: string]: unknown;
}

// ─── Goal Runtime State ──────────────────────────────────────────────────────

export interface GoalRuntimeStateSession {
  session_index: number;
  session_id: string;
  is_locked: boolean;
  can_open: boolean;
  can_complete: boolean;
  completion_block_reason: string | null;
  if_learned: boolean;
  is_mastered: boolean;
  mastery_score: number | null;
  mastery_threshold: number;
  navigation_mode: string;
}

export interface GoalRuntimeState {
  goal_id: number;
  adaptation: {
    suggested: boolean;
    message: string;
    sources: unknown[];
  };
  sessions: GoalRuntimeStateSession[];
}

// ─── Learning Content ────────────────────────────────────────────────────────

export interface ContentSection {
  title: string;
  anchor?: string;
  level?: number;
  markdown: string;
}

export interface ContentViewModel {
  sections?: ContentSection[];
  references?: Array<{ index: number; label: string }>;
}

export interface LearningContentResponse {
  document?: string | Record<string, unknown>;
  quizzes?: DocumentQuiz;
  content_format: 'standard' | 'audio_enhanced' | 'visual_enhanced';
  audio_url?: string | null;
  audio_mode?: string;
  view_model?: ContentViewModel;
  sources_used?: unknown[];
}

// ─── Content Generation ──────────────────────────────────────────────────────

export interface GenerateLearningContentRequest extends BaseRequest {
  learner_profile: string;
  learning_path: string;
  learning_session: string;
  use_search?: boolean;
  allow_parallel?: boolean;
  with_quiz?: boolean;
  goal_context?: Record<string, unknown>;
  user_id?: string;
  goal_id?: number;
  session_index?: number;
}

// ─── Session Activity ────────────────────────────────────────────────────────

export interface SessionActivityRequest {
  user_id: string;
  goal_id: number;
  session_index: number;
  event_type: 'start' | 'heartbeat' | 'end';
}

export interface SessionActivityResponse {
  trigger?: { show: boolean; message: string };
}

export interface CompleteSessionRequest {
  user_id: string;
  goal_id: number;
  session_index: number;
}

export interface CompleteSessionResponse {
  goal?: GoalAggregate;
}

export interface SubmitContentFeedbackRequest {
  user_id: string;
  goal_id: number;
  feedback: Record<string, unknown>;
}

export interface SubmitContentFeedbackResponse {
  goal?: GoalAggregate;
}

// ─── Dashboard Metrics ───────────────────────────────────────────────────────

export interface DashboardMetricsResponse {
  user_id: string;
  goal_id: number | null;
  overall_progress: number;
  skill_radar: {
    labels: string[];
    current_levels: number[];
    required_levels: number[];
  };
  session_time_series: Array<{ session_index: number; duration_sec: number }>;
  mastery_time_series: Array<{ session_index: number; mastery_pct: number }>;
}

// ─── Profile Updates ─────────────────────────────────────────────────────────

export interface LearnerInformationUpdateRequest extends BaseRequest {
  learner_profile: string;
  updated_learner_information: string;
  resume_text?: string;
  user_id?: string;
  goal_id?: number;
}
