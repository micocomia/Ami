from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, RootModel, field_validator, model_validator



class LevelRequired(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"


class LevelCurrent(str, Enum):
    unlearned = "unlearned"
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"



class SkillRequirement(BaseModel):
    name: str = Field(..., description="Actionable, concise skill name.")
    required_level: LevelRequired


class SkillRequirements(BaseModel):
    skill_requirements: List[SkillRequirement]

    @field_validator("skill_requirements")
    @classmethod
    def validate_length_and_uniqueness(cls, v: List[SkillRequirement]):
        if not (1 <= len(v) <= 10):
            raise ValueError("Number of skill requirements must be within 1 to 10.")
        seen = set()
        for item in v:
            key = item.name.strip().lower()
            if key in seen:
                raise ValueError(f'Duplicate skill name detected: "{item.name}".')
            seen.add(key)
        return v


class SkillGap(BaseModel):
    name: str
    is_gap: bool
    required_level: LevelRequired
    current_level: LevelCurrent
    reason: str = Field(..., description="≤20 words concise rationale for current level.")
    level_confidence: Confidence

    @field_validator("reason")
    @classmethod
    def limit_reason_words(cls, v: str) -> str:
        words = v.split()
        if len(words) > 20:
            raise ValueError("Reason must be 20 words or fewer.")
        return v

    @model_validator(mode="after")
    def check_gap_consistency(self):
        order = {"unlearned": 0, "beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}
        gap_should_be = order[self.current_level.value] < order[self.required_level.value]
        if self.is_gap != gap_should_be:
            raise ValueError(
                f'is_gap inconsistency: required="{self.required_level.value}", current="{self.current_level.value}" implies is_gap={gap_should_be}.'
            )
        return self


class GoalAssessment(BaseModel):
    """Assessment of the learning goal's quality and actionability."""

    is_vague: bool = Field(default=False, description="Whether the goal is too vague to produce good skill mappings.")
    all_mastered: bool = Field(default=False, description="Whether the learner already masters all required skills.")
    suggestion: str = Field(default="", description="Actionable suggestion for the learner.")
    auto_refined: bool = Field(default=False, description="Whether the goal was automatically refined.")
    original_goal: Optional[str] = Field(default=None, description="The original goal before auto-refinement, if refined.")
    refined_goal: Optional[str] = Field(default=None, description="The refined goal after auto-refinement, if refined.")


class SkillGaps(BaseModel):
    skill_gaps: List[SkillGap]
    goal_assessment: Optional[GoalAssessment] = Field(default=None)

    @field_validator("skill_gaps")
    @classmethod
    def limit_length_and_names(cls, v: List[SkillGap]):
        if not (1 <= len(v) <= 10):
            raise ValueError("Number of skill gaps must be within 1 to 10.")
        seen = set()
        for item in v:
            key = item.name.strip().lower()
            if key in seen:
                raise ValueError(f'Duplicate skill name detected: "{item.name}".')
            seen.add(key)
        return v


class SkillGapsRoot(RootModel):
    root: List[SkillGap]


class RefinedLearningGoal(BaseModel):
    refined_goal: str


# ── Bias Auditor schemas ────────────────────────────────────────────

class BiasCategory(str, Enum):
    demographic_inference = "demographic_inference"
    prestige_bias = "prestige_bias"
    gender_assumption = "gender_assumption"
    age_assumption = "age_assumption"
    nationality_assumption = "nationality_assumption"
    stereotype_based = "stereotype_based"
    unsubstantiated_claim = "unsubstantiated_claim"


class BiasSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class BiasFlag(BaseModel):
    skill_name: str
    bias_category: BiasCategory
    severity: BiasSeverity
    explanation: str = Field(..., description="Max 40 words explaining the detected bias.")
    suggestion: str = Field(..., description="Max 30 words suggesting how to fix the bias.")

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


class ConfidenceCalibrationFlag(BaseModel):
    skill_name: str
    current_level: str
    level_confidence: str
    issue: str


_DEFAULT_ETHICAL_DISCLAIMER = (
    "These skill assessments are AI-generated inferences based on the information you provided. "
    "They may not fully reflect your actual abilities. Use them as a starting point, not a definitive evaluation."
)


class BiasAuditResult(BaseModel):
    bias_flags: List[BiasFlag] = Field(default_factory=list)
    confidence_calibration_flags: List[ConfidenceCalibrationFlag] = Field(default_factory=list)
    overall_bias_risk: BiasSeverity = BiasSeverity.low
    audited_skill_count: int = 0
    flagged_skill_count: int = 0
    ethical_disclaimer: str = Field(default=_DEFAULT_ETHICAL_DISCLAIMER)
