
from pydantic import BaseModel
from typing import Any, Dict, Optional


class BaseRequest(BaseModel):
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    method_name: str = "genmentor"


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


class TailoredContentGenerationRequest(BaseRequest):

    learner_profile: str
    learning_path: str
    knowledge_point: str


class KnowledgePerspectiveExplorationRequest(BaseRequest):

    learner_profile: str
    learning_path: str
    knowledge_point: str


class KnowledgePerspectiveDraftingRequest(BaseRequest):

    learner_profile: str
    learning_path: str
    knowledge_point: str
    perspectives_of_knowledge_point: str
    knowledge_perspective: str
    use_search: bool = True


class KnowledgeDocumentIntegrationRequest(BaseRequest):

    learner_profile: str
    learning_path: str
    knowledge_point: str
    perspectives_of_knowledge_point: str
    drafts_of_perspectives: str


class PointPerspectivesDraftingRequest(BaseModel):

    learner_profile: str
    learning_path: str
    knowledge_point: str
    perspectives_of_knowledge_point: str
    use_search: bool
    allow_parallel: bool
 

class KnowledgeQuizGenerationRequest(BaseModel):

    learner_profile: str
    learning_document: str
    single_choice_count: int = 3
    multiple_choice_count: int = 0
    true_false_count: int = 0
    short_answer_count: int = 0
    open_ended_count: int = 0


class TailoredContentGenerationRequest(BaseModel):

    learner_profile: str
    learning_path: str
    learning_session: str
    use_search: bool = True
    allow_parallel: bool = True
    with_quiz: bool = True


class KnowledgePointExplorationRequest(BaseModel):
    
    learner_profile: str
    learning_path: str
    learning_session: str


class KnowledgePointDraftingRequest(BaseModel):

    learner_profile: str
    learning_path: str
    learning_session: str
    knowledge_points: str
    knowledge_point: str
    use_search: bool


class KnowledgePointsDraftingRequest(BaseModel):

    learner_profile: str
    learning_path: str
    learning_session: str
    knowledge_points: str
    use_search: bool
    allow_parallel: bool


class LearningDocumentIntegrationRequest(BaseModel):

    learner_profile: str
    learning_path: str
    learning_session: str
    knowledge_points: str
    knowledge_drafts: str
    output_markdown: bool = False


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
