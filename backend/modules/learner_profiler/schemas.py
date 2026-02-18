from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, RootModel, computed_field, field_validator


class RequiredLevel(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"


class CurrentLevel(str, Enum):
    unlearned = "unlearned"
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"


class MasteredSkill(BaseModel):
    name: str
    proficiency_level: RequiredLevel


class InProgressSkill(BaseModel):
    name: str
    required_proficiency_level: RequiredLevel
    current_proficiency_level: CurrentLevel


class CognitiveStatus(BaseModel):
    overall_progress: int = Field(..., ge=0, le=100)
    mastered_skills: List[MasteredSkill] = Field(default_factory=list)
    in_progress_skills: List[InProgressSkill] = Field(default_factory=list)


class FSLSMDimensions(BaseModel):
    fslsm_processing: float = Field(0.0, ge=-1, le=1)     # -1 active ↔ 1 reflective
    fslsm_perception: float = Field(0.0, ge=-1, le=1)     # -1 sensing ↔ 1 intuitive
    fslsm_input: float = Field(0.0, ge=-1, le=1)          # -1 visual ↔ 1 verbal
    fslsm_understanding: float = Field(0.0, ge=-1, le=1)  # -1 sequential ↔ 1 global


def derive_content_style(dims: FSLSMDimensions) -> str:
    """Derive content style from perception + understanding dimensions."""
    parts: list[str] = []
    # perception: sensing (-1) → concrete/practical; intuitive (+1) → conceptual/theoretical
    if dims.fslsm_perception <= -0.3:
        parts.append("concrete examples and practical applications")
    elif dims.fslsm_perception >= 0.3:
        parts.append("conceptual and theoretical explanations")
    else:
        parts.append("a mix of practical and conceptual content")
    # understanding: sequential (-1) → step-by-step; global (+1) → big-picture
    if dims.fslsm_understanding <= -0.3:
        parts.append("presented in step-by-step sequences")
    elif dims.fslsm_understanding >= 0.3:
        parts.append("with big-picture overviews first")
    else:
        parts.append("balancing sequential detail and big-picture context")
    return parts[0][0].upper() + parts[0][1:] + ", " + parts[1]


def derive_activity_type(dims: FSLSMDimensions) -> str:
    """Derive activity type from processing + input dimensions."""
    parts: list[str] = []
    # processing: active (-1) → hands-on/interactive; reflective (+1) → reading/observation
    if dims.fslsm_processing <= -0.3:
        parts.append("hands-on and interactive activities")
    elif dims.fslsm_processing >= 0.3:
        parts.append("reading and observation-based learning")
    else:
        parts.append("a balance of interactive and reflective activities")
    # input: visual (-1) → diagrams/videos; verbal (+1) → text/lectures
    if dims.fslsm_input <= -0.3:
        parts.append("with diagrams, charts, and videos")
    elif dims.fslsm_input >= 0.3:
        parts.append("with text-based materials and lectures")
    else:
        parts.append("using both visual and verbal materials")
    return parts[0][0].upper() + parts[0][1:] + ", " + parts[1]


class LearningPreferences(BaseModel):
    fslsm_dimensions: FSLSMDimensions = Field(default_factory=FSLSMDimensions)
    additional_notes: str | None = None

    @computed_field
    @property
    def content_style(self) -> str:
        return derive_content_style(self.fslsm_dimensions)

    @computed_field
    @property
    def activity_type(self) -> str:
        return derive_activity_type(self.fslsm_dimensions)


class BehavioralPatterns(BaseModel):
    system_usage_frequency: str
    session_duration_engagement: str
    motivational_triggers: str | None = None
    additional_notes: str | None = None


class LearnerProfile(BaseModel):
    learner_information: str
    learning_goal: str
    goal_display_name: str = ""
    cognitive_status: CognitiveStatus
    learning_preferences: LearningPreferences
    behavioral_patterns: BehavioralPatterns

    @field_validator("learning_goal")
    @classmethod
    def ensure_nonempty_goal(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("learning_goal must be non-empty")
        return v


# ── Fairness Validator schemas ──────────────────────────────────────

class FairnessCategory(str, Enum):
    fslsm_unjustified_deviation = "fslsm_unjustified_deviation"
    solo_missing_justification = "solo_missing_justification"
    confidence_without_evidence = "confidence_without_evidence"
    stereotypical_language = "stereotypical_language"


class FairnessSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class FairnessFlag(BaseModel):
    field_name: str
    fairness_category: FairnessCategory
    severity: FairnessSeverity
    explanation: str = Field(..., description="Max 40 words explaining the detected issue.")
    suggestion: str = Field(..., description="Max 30 words suggesting how to fix the issue.")

    @field_validator("explanation")
    @classmethod
    def limit_explanation_words(cls, v: str) -> str:
        if len(v.split()) > 40:
            raise ValueError("Explanation must be 40 words or fewer.")
        return v

    @field_validator("suggestion")
    @classmethod
    def limit_suggestion_words(cls, v: str) -> str:
        if len(v.split()) > 30:
            raise ValueError("Suggestion must be 30 words or fewer.")
        return v


class FSLSMDeviationFlag(BaseModel):
    dimension: str
    persona_value: float
    profile_value: float
    deviation: float
    issue: str


_DEFAULT_PROFILE_DISCLAIMER = (
    "This learner profile was generated by AI based on limited information. "
    "Learning style preferences and proficiency levels are estimates and may not "
    "fully represent your actual preferences or abilities."
)


class ProfileFairnessResult(BaseModel):
    fairness_flags: List[FairnessFlag] = Field(default_factory=list)
    fslsm_deviation_flags: List[FSLSMDeviationFlag] = Field(default_factory=list)
    overall_fairness_risk: FairnessSeverity = FairnessSeverity.low
    checked_fields_count: int = 0
    flagged_fields_count: int = 0
    ethical_disclaimer: str = Field(default=_DEFAULT_PROFILE_DISCLAIMER)
