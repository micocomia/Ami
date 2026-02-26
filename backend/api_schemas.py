
from pydantic import BaseModel
from typing import Any, Dict, Optional


class BaseRequest(BaseModel):
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    method_name: str = "ami"


class ChatWithAutorRequest(BaseRequest):

    messages: str
    learner_profile: str = ""


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


class LearningPathSchedulingRequest(BaseRequest):

    learner_profile: str
    session_count: int


class LearningPathReschedulingRequest(BaseRequest):
    
    learner_profile: str
    learning_path: str
    session_count: int = -1
    other_feedback: str = ""


class LearningContentGenerationRequest(BaseRequest):

    learner_profile: str
    learning_path: str
    learning_session: str
    use_search: bool = True
    allow_parallel: bool = True
    with_quiz: bool = True
    goal_context: Optional[Any] = None


class KnowledgePointDraftingRequest(BaseModel):

    learner_profile: str
    learning_path: str
    learning_session: str
    knowledge_points: str
    knowledge_point: str
    use_search: bool
    goal_context: Optional[Any] = None


class LearningContentFeedbackRequest(BaseRequest):

    learner_profile: str
    learning_content: str

class BiasAuditRequest(BaseRequest):

    learner_information: str
    skill_gaps: str


class ProfileFairnessRequest(BaseRequest):

    learner_profile: str
    learner_information: str
    persona_name: str = ""


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
