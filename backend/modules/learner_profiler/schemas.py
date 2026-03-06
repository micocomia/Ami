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

    @field_validator("overall_progress", mode="before")
    @classmethod
    def coerce_progress_to_int(cls, v):
        if isinstance(v, float):
            return int(round(v))
        return v


class FSLSMDimensions(BaseModel):
    fslsm_processing: float = Field(0.0, ge=-1, le=1)     # -1 active ↔ 1 reflective
    fslsm_perception: float = Field(0.0, ge=-1, le=1)     # -1 sensing ↔ 1 intuitive
    fslsm_input: float = Field(0.0, ge=-1, le=1)          # -1 visual ↔ 1 verbal
    fslsm_understanding: float = Field(0.0, ge=-1, le=1)  # -1 sequential ↔ 1 global


def derive_content_style(dims: FSLSMDimensions) -> str:
    """Derive content style from perception + understanding dimensions (5 bands each)."""
    parts: list[str] = []
    # perception: sensing (-1) → concrete/practical; intuitive (+1) → conceptual/theoretical
    if dims.fslsm_perception <= -0.7:
        parts.append("concrete examples and practical applications")
    elif dims.fslsm_perception <= -0.3:
        parts.append("primarily practical content with some conceptual grounding")
    elif dims.fslsm_perception >= 0.7:
        parts.append("conceptual and theoretical explanations")
    elif dims.fslsm_perception >= 0.3:
        parts.append("primarily conceptual content with practical examples")
    else:
        parts.append("a mix of practical and conceptual content")
    # understanding: sequential (-1) → step-by-step; global (+1) → big-picture
    if dims.fslsm_understanding <= -0.7:
        parts.append("presented in strict step-by-step sequences")
    elif dims.fslsm_understanding <= -0.3:
        parts.append("presented in a structured, sequential order")
    elif dims.fslsm_understanding >= 0.7:
        parts.append("with big-picture overviews first")
    elif dims.fslsm_understanding >= 0.3:
        parts.append("with big-picture framing before sequential detail")
    else:
        parts.append("balancing sequential detail and big-picture context")
    return parts[0][0].upper() + parts[0][1:] + ", " + parts[1]


def derive_activity_type(dims: FSLSMDimensions) -> str:
    """Derive activity type from processing + input dimensions (5 bands each)."""
    parts: list[str] = []
    # processing: active (-1) → hands-on/interactive; reflective (+1) → reading/observation
    if dims.fslsm_processing <= -0.7:
        parts.append("hands-on and interactive activities")
    elif dims.fslsm_processing <= -0.3:
        parts.append("primarily interactive activities with opportunities to practice")
    elif dims.fslsm_processing >= 0.7:
        parts.append("reading and observation-based learning")
    elif dims.fslsm_processing >= 0.3:
        parts.append("primarily reflective activities with some hands-on application")
    else:
        parts.append("a balance of interactive and reflective activities")
    # input: visual (-1) → diagrams/charts; verbal (+1) → written/narrated
    if dims.fslsm_input <= -0.7:
        parts.append("with diagrams, charts, and structured visual overviews")
    elif dims.fslsm_input <= -0.3:
        parts.append("with visual aids such as diagrams and charts")
    elif dims.fslsm_input >= 0.7:
        parts.append("with detailed written or narrated explanations")
    elif dims.fslsm_input >= 0.3:
        parts.append("with rich written and narrative-style content")
    else:
        parts.append("using both visual and verbal materials")
    return parts[0][0].upper() + parts[0][1:] + ", " + parts[1]


def derive_additional_notes(dims: FSLSMDimensions) -> str:
    """Derive a high-level learning preference summary from all four FSLSM dimensions.

    Only describes dimensions that cross the ±0.3 threshold. Descriptions align with
    the adaptations in the learning path scheduler but avoid implementation-specific
    terms (no checkpoint challenges, navigation modes, or podcast mentions).
    """
    notes: list[str] = []

    # Processing dimension
    if dims.fslsm_processing <= -0.7:
        notes.append("learns best through active engagement and practice")
    elif dims.fslsm_processing <= -0.3:
        notes.append("prefers hands-on activities with opportunities to apply concepts")
    elif dims.fslsm_processing >= 0.7:
        notes.append("prefers to reflect deeply on new concepts before proceeding")
    elif dims.fslsm_processing >= 0.3:
        notes.append("benefits from time to reflect before moving on")

    # Perception dimension
    if dims.fslsm_perception <= -0.7:
        notes.append("strongly prefers concrete examples and real-world applications before theory")
    elif dims.fslsm_perception <= -0.3:
        notes.append("tends to prefer practical examples introduced before theoretical concepts")
    elif dims.fslsm_perception >= 0.7:
        notes.append("prefers to grasp the big-picture theory and concepts first")
    elif dims.fslsm_perception >= 0.3:
        notes.append("tends to prefer understanding concepts before seeing examples")

    # Input dimension
    if dims.fslsm_input <= -0.7:
        notes.append("strongly prefers visual formats such as diagrams and structured visual overviews")
    elif dims.fslsm_input <= -0.3:
        notes.append("prefers visual aids like diagrams and charts to support understanding")
    elif dims.fslsm_input >= 0.7:
        notes.append("strongly prefers detailed written or narrated explanations over visual materials")
    elif dims.fslsm_input >= 0.3:
        notes.append("prefers rich written and narrative-style content, including spoken or narrated explanations")

    # Understanding dimension
    if dims.fslsm_understanding <= -0.7:
        notes.append("learns best with a strict step-by-step, sequential approach")
    elif dims.fslsm_understanding <= -0.3:
        notes.append("tends to prefer a structured, sequential progression through material")
    elif dims.fslsm_understanding >= 0.7:
        notes.append("strongly prefers to see the overall big picture before diving into specifics")
    elif dims.fslsm_understanding >= 0.3:
        notes.append("tends to prefer getting the big picture before exploring details")

    if not notes:
        return "No strong learning style preferences; balanced across all dimensions."

    notes[0] = notes[0][0].upper() + notes[0][1:]
    return "; ".join(notes) + "."


def refresh_learning_preferences_derived_fields(profile_dict: dict) -> None:
    """Refresh derived text fields in learning_preferences based on current FSLSM dims.

    Updates content_style, activity_type, and additional_notes in-place on the raw
    profile dict so they stay consistent with fslsm_dimensions in raw-dict code paths
    (e.g., adaptation engine, store) that don't go through the Pydantic model.

    No-op if learning_preferences is absent — avoids creating the key on minimal dicts.
    """
    if not isinstance(profile_dict, dict) or not isinstance(profile_dict.get("learning_preferences"), dict):
        return
    raw_dims = profile_dict["learning_preferences"].get("fslsm_dimensions", {})
    try:
        dims = FSLSMDimensions(**{k: float(raw_dims.get(k, 0.0) or 0.0) for k in (
            "fslsm_processing", "fslsm_perception", "fslsm_input", "fslsm_understanding"
        )})
    except Exception:
        return
    prefs = profile_dict["learning_preferences"]
    prefs["content_style"] = derive_content_style(dims)
    prefs["activity_type"] = derive_activity_type(dims)
    prefs["additional_notes"] = derive_additional_notes(dims)


class LearningPreferences(BaseModel):
    fslsm_dimensions: FSLSMDimensions = Field(default_factory=FSLSMDimensions)

    @computed_field
    @property
    def content_style(self) -> str:
        return derive_content_style(self.fslsm_dimensions)

    @computed_field
    @property
    def activity_type(self) -> str:
        return derive_activity_type(self.fslsm_dimensions)

    @computed_field
    @property
    def additional_notes(self) -> str:
        return derive_additional_notes(self.fslsm_dimensions)


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
