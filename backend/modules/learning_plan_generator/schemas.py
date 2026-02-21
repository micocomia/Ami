from __future__ import annotations

from enum import Enum
from typing import List, Optional, Sequence

from pydantic import BaseModel, Field, field_validator


class Proficiency(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"


class DesiredOutcome(BaseModel):
    name: str = Field(..., description="Skill name")
    level: Proficiency = Field(..., description="Desired proficiency when completed")


class SessionItem(BaseModel):
    id: str = Field(..., description="Session identifier, e.g., 'Session 1'")
    title: str
    abstract: str
    if_learned: bool
    associated_skills: List[str] = Field(default_factory=list)
    desired_outcome_when_completed: List[DesiredOutcome] = Field(default_factory=list)

    # Mastery tracking
    mastery_score: Optional[float] = Field(None, ge=0, le=100, description="Quiz score percentage, None if not yet attempted")
    is_mastered: bool = Field(False, description="True if mastery_score >= mastery_threshold")
    mastery_threshold: float = Field(70.0, ge=0, le=100, description="Per-session threshold based on required proficiency")

    # FSLSM-driven structural fields
    has_checkpoint_challenges: bool = Field(False, description="Active learners: mid-session checkpoint challenges")
    thinking_time_buffer_minutes: int = Field(0, ge=0, description="Reflective learners: recommended buffer time before next session")
    session_sequence_hint: Optional[str] = Field(None, description="Perception hint: 'application-first' or 'theory-first'")
    navigation_mode: str = Field("linear", description="'linear' (sequential) or 'free' (global)")

    @field_validator("associated_skills")
    @classmethod
    def ensure_nonempty_strings(cls, v: Sequence[str]) -> List[str]:
        return [s for s in (str(x).strip() for x in v) if s]


class QuizResult(BaseModel):
    session_id: str
    total_questions: int = Field(..., ge=1)
    correct_answers: int = Field(..., ge=0)
    score_percentage: float = Field(..., ge=0, le=100)


class LearningPath(BaseModel):
    learning_path: List[SessionItem]

    @field_validator("learning_path")
    @classmethod
    def limit_sessions(cls, v: List[SessionItem]) -> List[SessionItem]:
        if not (1 <= len(v) <= 10):
            raise ValueError("Learning path must contain between 1 and 10 sessions.")
        return v
