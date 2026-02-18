from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, TypeAlias

from pydantic import BaseModel, Field
from base import BaseAgent
from ..prompts.bias_auditor import bias_auditor_system_prompt, bias_auditor_task_prompt
from ..schemas import BiasAuditResult, ConfidenceCalibrationFlag, BiasSeverity

logger = logging.getLogger(__name__)

JSONDict: TypeAlias = Dict[str, Any]

# Extreme levels that are suspicious when paired with low confidence
_EXTREME_LEVELS = {"unlearned", "expert"}


class BiasAuditPayload(BaseModel):
    """Validated input for the bias auditor."""
    learner_information: str = Field(...)
    skill_gaps: dict = Field(...)


class BiasAuditor(BaseAgent):
    """Post-processing agent that audits skill gap assessments for bias."""

    name: str = "BiasAuditor"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=bias_auditor_system_prompt,
            jsonalize_output=True,
        )

    def audit_skill_gaps(self, input_dict: dict) -> JSONDict:
        """Run bias audit on skill gap results.

        Args:
            input_dict: Must contain 'learner_information' (str) and 'skill_gaps' (dict).
                        The 'skill_gaps' dict should have a 'skill_gaps' key with a list of gap dicts.

        Returns:
            A BiasAuditResult dict.
        """
        payload = BiasAuditPayload(**input_dict)

        # Serialize skill_gaps for the prompt
        prompt_vars = {
            "learner_information": payload.learner_information,
            "skill_gaps": json.dumps(payload.skill_gaps, indent=2),
        }

        # LLM call — returns bias_flags + overall_bias_risk
        raw_output = self.invoke(prompt_vars, task_prompt=bias_auditor_task_prompt)

        llm_bias_flags = raw_output.get("bias_flags", [])
        llm_overall_risk = raw_output.get("overall_bias_risk", "low")

        # Deterministic confidence calibration check
        skill_gaps_list = payload.skill_gaps.get("skill_gaps", [])
        calibration_flags = self._check_confidence_calibration(skill_gaps_list)

        # Compute counts
        audited_skill_count = len(skill_gaps_list)
        flagged_skill_names = set()
        for flag in llm_bias_flags:
            flagged_skill_names.add(flag.get("skill_name", ""))
        for flag in calibration_flags:
            flagged_skill_names.add(flag.skill_name)
        flagged_skill_names.discard("")
        flagged_skill_count = len(flagged_skill_names)

        # Promote risk if calibration flags exist but LLM said low
        overall_bias_risk = llm_overall_risk
        if calibration_flags and overall_bias_risk == "low":
            overall_bias_risk = "medium"

        # Validate and return
        result = BiasAuditResult(
            bias_flags=llm_bias_flags,
            confidence_calibration_flags=[f.model_dump() for f in calibration_flags],
            overall_bias_risk=overall_bias_risk,
            audited_skill_count=audited_skill_count,
            flagged_skill_count=flagged_skill_count,
        )
        return result.model_dump()

    @staticmethod
    def _check_confidence_calibration(
        skill_gaps: List[Dict[str, Any]],
    ) -> List[ConfidenceCalibrationFlag]:
        """Flag skills with low confidence paired with extreme levels."""
        flags: List[ConfidenceCalibrationFlag] = []
        for gap in skill_gaps:
            confidence = gap.get("level_confidence", "").lower()
            current_level = gap.get("current_level", "").lower()
            if confidence == "low" and current_level in _EXTREME_LEVELS:
                flags.append(
                    ConfidenceCalibrationFlag(
                        skill_name=gap.get("name", "Unknown"),
                        current_level=current_level,
                        level_confidence=confidence,
                        issue=(
                            f"Low confidence assessment assigned extreme level '{current_level}'. "
                            f"Consider defaulting to a moderate level when confidence is low."
                        ),
                    )
                )
        return flags


def audit_skill_gap_bias_with_llm(
    llm: Any,
    learner_information: str,
    skill_gaps: dict,
) -> JSONDict:
    """Convenience function: create a BiasAuditor and run the audit."""
    auditor = BiasAuditor(llm)
    return auditor.audit_skill_gaps({
        "learner_information": learner_information,
        "skill_gaps": skill_gaps,
    })
