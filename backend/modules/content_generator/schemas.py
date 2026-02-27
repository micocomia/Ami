from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional, Literal

from pydantic import BaseModel, Field, field_validator


class KnowledgeRole(str, Enum):
    foundational = "foundational"
    practical = "practical"
    strategic = "strategic"


class KnowledgeSoloLevel(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"


class KnowledgePoint(BaseModel):
    name: str
    role: KnowledgeRole
    solo_level: KnowledgeSoloLevel


class KnowledgePoints(BaseModel):
    knowledge_points: List[KnowledgePoint]

class KnowledgeDraft(BaseModel):
    title: str
    content: str
    sources_used: Optional[List[dict]] = None


class KnowledgeDraftEvaluationFeedback(BaseModel):
    coherence: str
    content_completeness: str
    personalization: str
    solo_alignment: str


class KnowledgeDraftEvaluation(BaseModel):
    feedback: KnowledgeDraftEvaluationFeedback
    is_acceptable: bool = Field(default=True)
    issues: List[str] = Field(default_factory=list)
    improvement_directives: str = Field(default="")

    @field_validator("improvement_directives", mode="before")
    @classmethod
    def coerce_improvement_directives(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            parts = [str(item).strip() for item in value if str(item).strip()]
            return "\n".join(parts)
        return str(value).strip()


class BatchKnowledgeDraftEvaluationItem(BaseModel):
    draft_id: str
    is_acceptable: bool = True
    issues: List[str] = Field(default_factory=list)
    improvement_directives: str = ""

    @field_validator("improvement_directives", mode="before")
    @classmethod
    def coerce_batch_improvement_directives(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            parts = [str(item).strip() for item in value if str(item).strip()]
            return "\n".join(parts)
        return str(value).strip()


class BatchKnowledgeDraftEvaluation(BaseModel):
    evaluations: List[BatchKnowledgeDraftEvaluationItem] = Field(default_factory=list)


class DraftQualityRecord(BaseModel):
    draft_id: str
    deterministic_pass: bool = False
    llm_pass: Optional[bool] = None
    issues: List[str] = Field(default_factory=list)
    directives: str = ""
    attempt_count: int = 1
    status: str = "pending"


class DocumentStructure(BaseModel):
    title: str
    overview: str
    summary: str


class SingleChoiceQuestion(BaseModel):
    question: str
    options: List[str]
    correct_option: int | str
    explanation: str | None = None


class MultipleChoiceQuestion(BaseModel):
    question: str
    options: List[str]
    correct_options: List[int | str]
    explanation: str | None = None


class TrueFalseQuestion(BaseModel):
    question: str
    correct_answer: bool
    explanation: str | None = None


class ShortAnswerQuestion(BaseModel):
    question: str
    expected_answer: str
    explanation: str | None = None


class OpenEndedQuestion(BaseModel):
    question: str
    rubric: str  # SOLO-aligned rubric: what constitutes each SOLO level for this question
    example_answer: str  # Model answer at the Relational/Extended Abstract level
    explanation: str | None = None


class DocumentQuiz(BaseModel):
    single_choice_questions: List[SingleChoiceQuestion] = Field(default_factory=list)
    multiple_choice_questions: List[MultipleChoiceQuestion] = Field(default_factory=list)
    true_false_questions: List[TrueFalseQuestion] = Field(default_factory=list)
    short_answer_questions: List[ShortAnswerQuestion] = Field(default_factory=list)
    open_ended_questions: List[OpenEndedQuestion] = Field(default_factory=list)


def parse_knowledge_points(data) -> KnowledgePoints:
    return KnowledgePoints.model_validate(data)


def parse_knowledge_draft(data) -> KnowledgeDraft:
    return KnowledgeDraft.model_validate(data)


def parse_document_structure(data) -> DocumentStructure:
    return DocumentStructure.model_validate(data)


def parse_document_quiz(data) -> DocumentQuiz:
    return DocumentQuiz.model_validate(data)


class MediaRelevanceResult(BaseModel):
    keep: bool = True
    display_title: str = ""
    short_description: str = ""
    confidence: Optional[float] = None


class MediaRelevanceBatchResult(BaseModel):
    relevance: List[MediaRelevanceResult] = Field(default_factory=list)

    @field_validator("relevance", mode="before")
    @classmethod
    def coerce_boolean_relevance_list(cls, value: Any) -> Any:
        # Backward compatibility for older evaluator outputs: {"relevance":[true,false]}
        if isinstance(value, list) and value and all(isinstance(item, bool) for item in value):
            return [{"keep": item} for item in value]
        return value


class MediaResource(BaseModel):
    type: str
    title: str
    url: str
    video_id: str = ""
    thumbnail_url: str = ""
    image_url: str = ""
    description: str = ""
    display_title: str = ""
    short_description: str = ""


class IntegratedQualityRecord(BaseModel):
    is_acceptable: bool = True
    issues: List[str] = Field(default_factory=list)
    directives: str = ""
    repair_scope: Literal["integrator_only", "section_redraft", "full_restart_required"] = "integrator_only"
    affected_section_indices: List[int] = Field(default_factory=list)
    attempt_count: int = 1


class IntegratedDocumentEvaluation(BaseModel):
    is_acceptable: bool = True
    issues: List[str] = Field(default_factory=list)
    improvement_directives: str = ""
    repair_scope: Literal["integrator_only", "section_redraft", "full_restart_required"] = "integrator_only"
    affected_section_indices: List[int] = Field(default_factory=list)
    severity: Literal["low", "medium", "high"] = "medium"

    @field_validator("repair_scope", mode="before")
    @classmethod
    def coerce_repair_scope(cls, value: Any) -> str:
        scope = str(value or "").strip().lower()
        if scope in {"integrator_only", "section_redraft", "full_restart_required"}:
            return scope
        return "integrator_only"

    @field_validator("severity", mode="before")
    @classmethod
    def coerce_severity(cls, value: Any) -> str:
        sev = str(value or "").strip().lower()
        if sev in {"low", "medium", "high"}:
            return sev
        return "medium"


class OrchestrationQualityTrace(BaseModel):
    trace_id: str
    draft_records: List[DraftQualityRecord] = Field(default_factory=list)
    integration_records: List[IntegratedQualityRecord] = Field(default_factory=list)
    draft_evaluator_status: str = "ok"
    quality_checkpoint_passed: bool = False
    draft_stage_degraded: bool = False
    accepted_draft_ratio: float = 0.0
    explorer_terminal_failure: bool = False
    fallback_mode: Optional[str] = None
    final_failure_reason: str = ""
    severity: Literal["low", "medium", "high"] = "low"
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)


class ContentSection(BaseModel):
    title: str
    summary: str


class ContentOutline(BaseModel):
    title: str
    sections: List[ContentSection] = Field(default_factory=list)


class QuizPair(BaseModel):
    question: str
    answer: str


class LearningContent(BaseModel):
    title: str
    overview: str
    content: str
    summary: str
    quizzes: List[QuizPair] = Field(default_factory=list)


class FeedbackDetail(BaseModel):
    progression: str
    engagement: str
    personalization: str


class LearnerFeedback(BaseModel):
    feedback: FeedbackDetail
    suggestions: FeedbackDetail
