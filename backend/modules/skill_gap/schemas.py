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
