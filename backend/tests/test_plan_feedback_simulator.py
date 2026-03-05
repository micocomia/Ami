"""Tests for deterministic SOLO guardrails in plan feedback simulation.

Run from repo root:
    python -m pytest backend/tests/test_plan_feedback_simulator.py -v
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.learning_plan_generator.agents.plan_feedback_simulator import (
    LearningPlanFeedbackSimulator,
    _merge_feedback,
    build_deterministic_solo_audit,
)
from modules.learning_plan_generator.schemas import LLMQualityOutput


def _base_llm_output(
    *,
    quality_issues=None,
    quality_directives="",
    engagement_feedback="The learner would likely stay engaged.",
    personalization_feedback="The path is generally aligned to learner needs.",
):
    return {
        "feedback": {
            "engagement": engagement_feedback,
            "personalization": personalization_feedback,
        },
        "suggestions": {"engagement": "", "personalization": ""},
        "quality_issues": quality_issues or [],
        "quality_directives": quality_directives,
    }


def _valid_scaffold_path():
    return [
        {
            "id": "Session 3",
            "title": "Introduction to Functions",
            "desired_outcome_when_completed": [
                {"name": "Understanding and Using Functions", "level": "beginner"},
            ],
        },
        {
            "id": "Session 4",
            "title": "Basics of Code Decomposition",
            "desired_outcome_when_completed": [
                {"name": "Code Decomposition", "level": "beginner"},
            ],
        },
        {
            "id": "Session 5",
            "title": "Understanding Functions and Decomposition",
            "desired_outcome_when_completed": [
                {"name": "Understanding and Using Functions", "level": "intermediate"},
                {"name": "Code Decomposition", "level": "intermediate"},
            ],
        },
    ]


class TestDeterministicSOLOAudit:
    def test_valid_scaffold_has_no_violations(self):
        profile = {"cognitive_status": {"mastered_skills": [], "in_progress_skills": []}}
        audit = build_deterministic_solo_audit(profile, _valid_scaffold_path())

        assert audit["violation_count"] == 0
        assert audit["has_violations"] is False

    def test_unlearned_to_intermediate_is_violation(self):
        profile = {"cognitive_status": {"mastered_skills": [], "in_progress_skills": []}}
        path = [
            {
                "id": "Session 1",
                "title": "Jump Start",
                "desired_outcome_when_completed": [
                    {"name": "Functions", "level": "intermediate"},
                ],
            }
        ]

        audit = build_deterministic_solo_audit(profile, path)
        assert audit["violation_count"] == 1
        assert audit["violations"][0]["from_level"] == "unlearned"
        assert audit["violations"][0]["to_level"] == "intermediate"

    def test_beginner_to_advanced_is_violation(self):
        profile = {
            "cognitive_status": {
                "mastered_skills": [],
                "in_progress_skills": [
                    {
                        "name": "Abstraction in Programming",
                        "current_proficiency_level": "beginner",
                        "required_proficiency_level": "advanced",
                    }
                ],
            }
        }
        path = [
            {
                "id": "Session 1",
                "title": "Abstraction Sprint",
                "desired_outcome_when_completed": [
                    {"name": "Abstraction in Programming", "level": "advanced"},
                ],
            }
        ]

        audit = build_deterministic_solo_audit(profile, path)
        assert audit["violation_count"] == 1
        assert audit["violations"][0]["from_level"] == "beginner"
        assert audit["violations"][0]["to_level"] == "advanced"

    def test_path_not_reaching_required_level_is_coverage_gap(self):
        """Path advances correctly (no jumps) but stops before required_proficiency_level."""
        profile = {
            "cognitive_status": {
                "mastered_skills": [],
                "in_progress_skills": [
                    {
                        "name": "Python",
                        "current_proficiency_level": "unlearned",
                        "required_proficiency_level": "advanced",
                    }
                ],
            }
        }
        path = [
            {
                "id": "Session 1",
                "title": "Python Basics",
                "desired_outcome_when_completed": [
                    {"name": "Python", "level": "beginner"},
                ],
            },
            {
                "id": "Session 2",
                "title": "Python Intermediate",
                "desired_outcome_when_completed": [
                    {"name": "Python", "level": "intermediate"},
                ],
            },
        ]
        audit = build_deterministic_solo_audit(profile, path)
        # Transitions are correct (no SOLO skipping violations)
        assert audit["violation_count"] == 0
        # But path stops at "intermediate" when "advanced" is required
        assert audit["coverage_gap_count"] == 1
        assert audit["coverage_gaps"][0]["required_level"] == "advanced"
        assert audit["coverage_gaps"][0]["reached_level"] == "intermediate"

    def test_exact_skill_name_match_no_coverage_gap(self):
        """Exact skill name in path outcome matches profile → no coverage gap, no violation."""
        profile = {
            "cognitive_status": {
                "mastered_skills": [],
                "in_progress_skills": [
                    {
                        "name": "Understanding and Using Functions",
                        "current_proficiency_level": "beginner",
                        "required_proficiency_level": "intermediate",
                    }
                ],
            }
        }
        path = [
            {
                "id": "Session 1",
                "title": "Functions in Practice",
                "desired_outcome_when_completed": [
                    {"name": "Understanding and Using Functions", "level": "intermediate"},
                ],
            }
        ]

        audit = build_deterministic_solo_audit(profile, path)
        assert audit["violation_count"] == 0
        assert audit["coverage_gap_count"] == 0

    def test_mismatched_skill_name_treated_as_different_skill(self):
        """Different casing/punctuation → treated as a different skill; profile skill is flagged as coverage gap."""
        profile = {
            "cognitive_status": {
                "mastered_skills": [],
                "in_progress_skills": [
                    {
                        "name": "Understanding and Using Functions",
                        "current_proficiency_level": "beginner",
                        "required_proficiency_level": "intermediate",
                    }
                ],
            }
        }
        path = [
            {
                "id": "Session 1",
                "title": "Functions in Practice",
                "desired_outcome_when_completed": [
                    {"name": "understanding   using functions!!", "level": "intermediate"},
                ],
            }
        ]

        audit = build_deterministic_solo_audit(profile, path)
        assert audit["coverage_gap_count"] == 1
        assert audit["coverage_gaps"][0]["skill"] == "Understanding and Using Functions"


class TestFeedbackReconciliation:
    def test_feedback_path_coerces_list_improvement_directives(self, monkeypatch):
        def fake_invoke(self, input_dict, task_prompt=None, **kwargs):
            return _base_llm_output(
                quality_issues=["Needs better verbal scaffolding."],
                quality_directives=[
                    "Integrate verbal learning supports into earlier sessions.",
                    "Add clearer contextual examples for relevance.",
                ],
            )

        monkeypatch.setattr(LearningPlanFeedbackSimulator, "invoke", fake_invoke)

        simulator = LearningPlanFeedbackSimulator(MagicMock())
        output = simulator.feedback_path(
            {
                "learner_profile": {"cognitive_status": {"mastered_skills": [], "in_progress_skills": []}},
                "learning_path": _valid_scaffold_path(),
            }
        )

        assert isinstance(output["improvement_directives"], str)
        assert "Integrate verbal learning supports" in output["improvement_directives"]
        assert "Add clearer contextual examples" in output["improvement_directives"]

    def test_feedback_path_forces_unacceptable_when_violations_are_missed(self, monkeypatch):
        def fake_invoke(self, input_dict, task_prompt=None, **kwargs):
            return _base_llm_output(quality_issues=[])

        monkeypatch.setattr(LearningPlanFeedbackSimulator, "invoke", fake_invoke)

        simulator = LearningPlanFeedbackSimulator(MagicMock())
        output = simulator.feedback_path(
            {
                "learner_profile": {"cognitive_status": {"mastered_skills": [], "in_progress_skills": []}},
                "learning_path": [
                    {
                        "id": "Session 1",
                        "title": "Functions and Decomposition Deep Dive",
                        "desired_outcome_when_completed": [
                            {"name": "Understanding and Using Functions", "level": "advanced"},
                        ],
                    }
                ],
            }
        )

        assert output["is_acceptable"] is False
        assert any("SOLO progression skipped" in issue for issue in output["issues"])
        assert "at most one SOLO level" in output["improvement_directives"]
        assert "deterministic SOLO audit found" in output["feedback"]["progression"]

    def test_feedback_path_forces_unacceptable_when_coverage_gap(self, monkeypatch):
        """Plan is correctly paced but doesn't reach required level → must be unacceptable."""
        def fake_invoke(self, input_dict, task_prompt=None, **kwargs):
            return _base_llm_output(quality_issues=[])

        monkeypatch.setattr(LearningPlanFeedbackSimulator, "invoke", fake_invoke)

        profile = {
            "cognitive_status": {
                "mastered_skills": [],
                "in_progress_skills": [
                    {
                        "name": "Python",
                        "current_proficiency_level": "unlearned",
                        "required_proficiency_level": "advanced",
                    }
                ],
            }
        }
        path = [
            {"id": "Session 1", "title": "Basics", "desired_outcome_when_completed": [{"name": "Python", "level": "beginner"}]},
            {"id": "Session 2", "title": "Intermediate", "desired_outcome_when_completed": [{"name": "Python", "level": "intermediate"}]},
        ]
        simulator = LearningPlanFeedbackSimulator(MagicMock())
        output = simulator.feedback_path({"learner_profile": profile, "learning_path": path})

        assert output["is_acceptable"] is False
        assert any("advanced" in issue for issue in output["issues"])
        assert "advanced" in output["improvement_directives"] or "required" in output["improvement_directives"]

    def test_feedback_path_forces_unacceptable_on_session_overflow_truncation(self, monkeypatch):
        def fake_invoke(self, input_dict, task_prompt=None, **kwargs):
            return _base_llm_output(quality_issues=[])

        monkeypatch.setattr(LearningPlanFeedbackSimulator, "invoke", fake_invoke)

        simulator = LearningPlanFeedbackSimulator(MagicMock())
        output = simulator.feedback_path(
            {
                "learner_profile": {"cognitive_status": {"mastered_skills": [], "in_progress_skills": []}},
                "learning_path": _valid_scaffold_path(),
                "generation_observations": {
                    "raw_session_count": 25,
                    "effective_session_count": 20,
                    "was_trimmed": True,
                    "max_allowed_sessions": 20,
                },
            }
        )

        assert output["is_acceptable"] is False
        assert any("exceeded 20 sessions and was truncated" in issue for issue in output["issues"])
        assert "within 20 sessions" in output["improvement_directives"]


class TestMergeFeedback:
    def _make_llm_output(self, *, quality_issues=None, quality_directives=""):
        return LLMQualityOutput.model_validate(
            _base_llm_output(quality_issues=quality_issues, quality_directives=quality_directives)
        )

    def _clean_audit(self):
        return {
            "violations": [],
            "violation_count": 0,
            "coverage_gaps": [],
            "coverage_gap_count": 0,
        }

    def _violation_audit(self):
        return {
            "violations": [
                {
                    "session_id": "Session 1",
                    "session_index": 1,
                    "skill": "Functions",
                    "from_level": "unlearned",
                    "to_level": "advanced",
                    "delta": 3,
                }
            ],
            "violation_count": 1,
            "coverage_gaps": [],
            "coverage_gap_count": 0,
        }

    def test_clean_path_no_quality_issues_is_acceptable(self):
        llm_output = self._make_llm_output()
        result = _merge_feedback(llm_output, self._clean_audit(), {})
        assert result.is_acceptable is True
        assert result.issues == []

    def test_quality_issues_make_unacceptable(self):
        llm_output = self._make_llm_output(quality_issues=["FSLSM misalignment detected."])
        result = _merge_feedback(llm_output, self._clean_audit(), {})
        assert result.is_acceptable is False
        assert any("FSLSM misalignment" in issue for issue in result.issues)

    def test_quality_directives_list_coerced_to_string(self):
        llm_output = self._make_llm_output(
            quality_issues=["Engagement issue."],
            quality_directives=["Add more activities.", "Vary delivery format."],
        )
        result = _merge_feedback(llm_output, self._clean_audit(), {})
        assert isinstance(result.improvement_directives, str)
        assert "Add more activities" in result.improvement_directives
        assert "Vary delivery format" in result.improvement_directives

    def test_violations_make_unacceptable_with_solo_issues(self):
        llm_output = self._make_llm_output()
        result = _merge_feedback(llm_output, self._violation_audit(), {})
        assert result.is_acceptable is False
        assert any("SOLO progression skipped" in issue for issue in result.issues)
        assert "level-skipping" in result.feedback.progression

    def test_no_violations_progression_says_no_level_skipping(self):
        llm_output = self._make_llm_output()
        result = _merge_feedback(llm_output, self._clean_audit(), {})
        assert "no level-skipping transitions" in result.feedback.progression

    def test_session_overflow_makes_unacceptable_with_overflow_first(self):
        llm_output = self._make_llm_output()
        observations = {"was_trimmed": True, "raw_session_count": 25}
        result = _merge_feedback(llm_output, self._clean_audit(), observations)
        assert result.is_acceptable is False
        assert result.issues[0].startswith("Generated path exceeded")
        assert "within 20 sessions" in result.improvement_directives

    def test_structural_and_quality_issues_capped_at_three(self):
        # 2 structural (violation) + 2 quality = 4 total, should be capped to 3
        llm_output = self._make_llm_output(
            quality_issues=["FSLSM misalignment.", "Missing personalization."],
        )
        result = _merge_feedback(llm_output, self._violation_audit(), {})
        assert len(result.issues) <= 3
