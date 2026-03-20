from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, TypeAlias

from pydantic import BaseModel, Field
from base import BaseAgent
from ..prompts.content_bias_auditor import content_bias_auditor_system_prompt, content_bias_auditor_task_prompt
from ..schemas import ContentBiasAuditResult, ContentBiasFlag, ContentBiasSeverity, ContentBiasCategory

logger = logging.getLogger(__name__)

JSONDict: TypeAlias = Dict[str, Any]

# Known biased phrases mapped to suggested alternatives
_BIASED_PHRASES: Dict[str, str] = {
    # Gendered language
    "mankind": "humankind",
    "manmade": "artificial",
    "man-made": "artificial",
    "chairman": "chairperson",
    "policeman": "police officer",
    "fireman": "firefighter",
    "stewardess": "flight attendant",
    "businessman": "businessperson",
    "cameraman": "camera operator",
    "mailman": "mail carrier",
    "spokesman": "spokesperson",
    "housewife": "homemaker",
    "manpower": "workforce",
    "man hours": "person hours",
    "freshman": "first-year student",
    # Disability / ableist language
    "normal people": "most people",
    "suffers from": "lives with",
    "confined to a wheelchair": "uses a wheelchair",
    "the disabled": "people with disabilities",
    "the blind": "people who are blind",
    "the deaf": "people who are deaf",
    "crippled": "disabled",
    "lame": "inadequate",
    "blind spot": "oversight",
    "tone deaf": "insensitive",
    "crazy": "unexpected",
    "dumb": "uninformed",
    "mentally retarded": "intellectually disabled",
    "handicapped": "having a disability",
    # Cultural / racial
    "third world": "developing countries",
    "primitive": "traditional",
    "blacklist": "blocklist",
    "whitelist": "allowlist",
    "master/slave": "primary/replica",
    "master-slave": "primary-replica",
    "grandfathered": "legacy",
    "spirit animal": "inspiration",
}


class ContentBiasAuditPayload(BaseModel):
    """Validated input for the content bias auditor."""
    generated_content: str = Field(...)
    learner_information: str = Field(...)


class ContentBiasAuditor(BaseAgent):
    """Post-processing agent that audits generated learning content for bias."""

    name: str = "ContentBiasAuditor"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=content_bias_auditor_system_prompt,
            jsonalize_output=True,
        )

    def audit_content(self, input_dict: dict) -> JSONDict:
        """Run bias audit on generated learning content.

        Args:
            input_dict: Must contain 'generated_content' (str) and 'learner_information' (str).

        Returns:
            A ContentBiasAuditResult dict.
        """
        payload = ContentBiasAuditPayload(**input_dict)

        # LLM call
        prompt_vars = {
            "generated_content": payload.generated_content,
            "learner_information": payload.learner_information,
        }

        raw_output = self.invoke(prompt_vars, task_prompt=content_bias_auditor_task_prompt)

        llm_bias_flags = raw_output.get("bias_flags", [])
        llm_overall_risk = raw_output.get("overall_bias_risk", "low")

        # Deterministic biased language check
        deterministic_flags = self._check_biased_language(payload.generated_content)

        # Compute counts — count unique section titles flagged
        audited_section_count = self._count_sections(payload.generated_content)
        flagged_sections = set()
        for flag in llm_bias_flags:
            flagged_sections.add(flag.get("section_title", ""))
        for flag in deterministic_flags:
            flagged_sections.add(flag.section_title)
        flagged_sections.discard("")
        flagged_section_count = len(flagged_sections)

        # Promote risk if deterministic flags exist but LLM said low
        overall_bias_risk = llm_overall_risk
        if deterministic_flags and overall_bias_risk == "low":
            overall_bias_risk = "medium"

        # Validate and return
        result = ContentBiasAuditResult(
            bias_flags=llm_bias_flags,
            deterministic_flags=[f.model_dump() for f in deterministic_flags],
            overall_bias_risk=overall_bias_risk,
            audited_section_count=audited_section_count,
            flagged_section_count=flagged_section_count,
        )
        return result.model_dump()

    @staticmethod
    def _check_biased_language(content: str) -> List[ContentBiasFlag]:
        """Scan content for known biased phrases and return flags."""
        flags: List[ContentBiasFlag] = []
        content_lower = content.lower()
        for phrase, alternative in _BIASED_PHRASES.items():
            if re.search(r'\b' + re.escape(phrase) + r'\b', content_lower):
                flags.append(
                    ContentBiasFlag(
                        section_title="(full content scan)",
                        bias_category=ContentBiasCategory.language_bias,
                        severity=ContentBiasSeverity.low,
                        explanation=(
                            f"The phrase \"{phrase}\" was detected in the content. "
                            f"This may be considered non-inclusive language."
                        ),
                        suggestion=f"Consider replacing with \"{alternative}\".",
                    )
                )
        return flags

    @staticmethod
    def _count_sections(content: str) -> int:
        """Estimate the number of content sections from markdown headers."""
        headers = re.findall(r'^#{1,3}\s+.+', content, re.MULTILINE)
        return max(len(headers), 1)


def audit_content_bias_with_llm(
    llm: Any,
    generated_content: str,
    learner_information: str,
) -> JSONDict:
    """Convenience function: create a ContentBiasAuditor and run the audit."""
    auditor = ContentBiasAuditor(llm)
    return auditor.audit_content({
        "generated_content": generated_content,
        "learner_information": learner_information,
    })
