
from pydantic import BaseModel
from typing import Any, Dict, Optional


class BaseRequest(BaseModel):
    pass


class ChatWithAutorRequest(BaseRequest):

    messages: str
    learner_profile: str = ""
    user_id: Optional[str] = None
    goal_id: Optional[int] = None
    session_index: Optional[int] = None
    use_search: Optional[bool] = None
    use_vector_retrieval: Optional[bool] = None
    use_web_search: Optional[bool] = None
    use_media_search: Optional[bool] = None
    allow_preference_updates: Optional[bool] = None
    top_k: Optional[int] = None
    return_metadata: bool = False
    learner_information: Optional[str] = None


class LearningGoalRefinementRequest(BaseRequest):

    learning_goal: str
    learner_information: str = ""


class SkillGapIdentificationRequest(BaseRequest):

    learning_goal: str
    learner_information: str
    skill_requirements: Optional[str] = None


class LearnerProfileInitializationWithInfoRequest(BaseRequest):

    learning_goal: str
    learner_information: str
    skill_gaps: str
    user_id: Optional[str] = None
    goal_id: Optional[int] = None


class LearnerProfileUpdateRequest(BaseRequest):

    learner_profile: str
    learner_interactions: str
    learner_information: str = ""
    session_information: str = ""
    user_id: Optional[str] = None
    goal_id: Optional[int] = None


class CognitiveStatusUpdateRequest(BaseRequest):

    learner_profile: str
    session_information: str
    user_id: Optional[str] = None
    goal_id: Optional[int] = None


class LearningPreferencesUpdateRequest(BaseRequest):

    learner_profile: str
    learner_interactions: str
    learner_information: str = ""
    user_id: Optional[str] = None
    goal_id: Optional[int] = None


class LearnerInformationUpdateRequest(BaseRequest):

    learner_profile: str
    edited_learner_information: str = ""
    resume_text: str = ""
    user_id: Optional[str] = None
    goal_id: Optional[int] = None


class LearningPathSchedulingRequest(BaseRequest):

    learner_profile: str
    session_count: int


class LearningContentGenerationRequest(BaseRequest):

    learner_profile: str
    learning_path: str
    learning_session: str
    use_search: bool = True
    allow_parallel: bool = True
    with_quiz: bool = True
    goal_context: Optional[Any] = None
    user_id: Optional[str] = None
    goal_id: Optional[int] = None
    session_index: Optional[int] = None


class GoalCreateRequest(BaseModel):
    learning_goal: str
    skill_gaps: Any = []
    goal_assessment: Optional[Any] = None
    goal_context: Optional[Any] = None
    retrieved_sources: Any = []
    bias_audit: Optional[Any] = None
    profile_fairness: Optional[Any] = None
    learning_path: Any = []
    plan_agent_metadata: Optional[Any] = None
    learner_profile: Optional[Any] = None
    is_completed: bool = False
    is_deleted: bool = False


class GoalUpdateRequest(BaseModel):
    learning_goal: Optional[str] = None
    skill_gaps: Optional[Any] = None
    goal_assessment: Optional[Any] = None
    goal_context: Optional[Any] = None
    retrieved_sources: Optional[Any] = None
    bias_audit: Optional[Any] = None
    profile_fairness: Optional[Any] = None
    learning_path: Optional[Any] = None
    plan_agent_metadata: Optional[Any] = None
    is_completed: Optional[bool] = None
    is_deleted: Optional[bool] = None


class SessionActivityRequest(BaseModel):
    user_id: str
    goal_id: int
    session_index: int
    event_type: str
    event_time: Optional[str] = None


class CompleteSessionRequest(BaseRequest):
    user_id: str
    goal_id: int
    session_index: int
    session_end_time: Optional[str] = None


class SubmitContentFeedbackRequest(BaseRequest):
    user_id: str
    goal_id: int
    feedback: Any

class BiasAuditRequest(BaseRequest):

    learner_information: str
    skill_gaps: str


class ProfileFairnessRequest(BaseRequest):

    learner_profile: str
    learner_information: str
    persona_name: str = ""


class ContentBiasAuditRequest(BaseRequest):

    generated_content: str
    learner_information: str


class ChatbotBiasAuditRequest(BaseRequest):

    tutor_responses: str
    learner_information: str


class AuthRegisterRequest(BaseModel):
    username: str
    password: str


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class UserStateRequest(BaseModel):
    state: Dict[str, Any]


class MasteryEvaluationRequest(BaseModel):
    user_id: str
    goal_id: int
    session_index: int
    quiz_answers: Dict[str, Any]


class ResetMasteryAttemptRequest(BaseModel):
    user_id: str
    goal_id: int
    session_index: int


class BehavioralMetricsResponse(BaseModel):
    user_id: str
    goal_id: Optional[int] = None
    sessions_completed: int
    total_sessions_in_path: int
    sessions_learned: int
    avg_session_duration_sec: float
    total_learning_time_sec: float
    motivational_triggers_count: int
    mastery_history: list
    latest_mastery_rate: Optional[float] = None


class AutoProfileUpdateRequest(BaseModel):
    user_id: str
    goal_id: int = 0

    # only needed if this is the FIRST time we create the profile
    learning_goal: Optional[str] = None
    learner_information: Optional[Any] = None
    skill_gaps: Optional[Any] = None

    # optional session metadata
    session_information: Optional[Dict[str, Any]] = None


class AdaptLearningPathRequest(BaseRequest):
    """Request for adaptive plan regeneration."""
    user_id: str
    goal_id: int
    new_learner_profile: Optional[str] = None
    force: bool = False
