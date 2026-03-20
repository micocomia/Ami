from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, TypeAlias

from pydantic import BaseModel, Field
from base import BaseAgent
from ..prompts.chatbot_bias_auditor import chatbot_bias_auditor_system_prompt, chatbot_bias_auditor_task_prompt
from ..schemas import ChatbotBiasAuditResult, ChatbotBiasFlag, ChatbotBiasSeverity, ChatbotBiasCategory

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

# Patronizing phrases that may indicate tone bias
_PATRONIZING_PHRASES: List[str] = [
    "as i'm sure you know",
    "as i am sure you know",
    "this is really simple",
    "this is very simple",
    "this is easy",
    "this should be obvious",
    "obviously",
    "even you can",
    "anyone can understand",
    "it's not that hard",
    "surely you know",
    "you should already know",
    "as a beginner you wouldn't",
    "don't worry, it's simple",
    "let me dumb it down",
    "i'll make it simple for you",
    "you probably don't understand",
    "just think about it",
    "that's a basic concept",
    "this is trivial",
    "as i already explained",
    "you're overthinking this",
    "it's common sense",
    "even a child could",
    "surely you can see",
]


class ChatbotBiasAuditPayload(BaseModel):
    """Validated input for the chatbot bias auditor."""
    tutor_responses: str = Field(...)
    learner_information: str = Field(...)


class ChatbotBiasAuditor(BaseAgent):
    """Post-processing agent that audits AI tutor chatbot responses for bias."""

    name: str = "ChatbotBiasAuditor"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=chatbot_bias_auditor_system_prompt,
            jsonalize_output=True,
        )

    def audit_responses(self, input_dict: dict) -> JSONDict:
        """Run bias audit on tutor chatbot responses.

        Args:
            input_dict: Must contain 'tutor_responses' (str) and 'learner_information' (str).

        Returns:
            A ChatbotBiasAuditResult dict.
        """
        payload = ChatbotBiasAuditPayload(**input_dict)

        # LLM call
        prompt_vars = {
            "tutor_responses": payload.tutor_responses,
            "learner_information": payload.learner_information,
        }

        raw_output = self.invoke(prompt_vars, task_prompt=chatbot_bias_auditor_task_prompt)

        llm_bias_flags = raw_output.get("bias_flags", [])
        llm_overall_risk = raw_output.get("overall_bias_risk", "low")

        # Deterministic checks
        language_flags = self._check_biased_language(payload.tutor_responses)
        patronizing_flags = self._check_patronizing_language(payload.tutor_responses)
        deterministic_flags = language_flags + patronizing_flags

        # Count audited and flagged messages
        audited_message_count = self._count_tutor_messages(payload.tutor_responses)
        flagged_indices = set()
        for flag in llm_bias_flags:
            flagged_indices.add(flag.get("message_index", 0))
        for flag in deterministic_flags:
            flagged_indices.add(flag.message_index)
        flagged_message_count = len(flagged_indices)

        # Promote risk if deterministic flags exist but LLM said low
        overall_bias_risk = llm_overall_risk
        if deterministic_flags and overall_bias_risk == "low":
            overall_bias_risk = "medium"

        # Validate and return
        result = ChatbotBiasAuditResult(
            bias_flags=llm_bias_flags,
            deterministic_flags=[f.model_dump() for f in deterministic_flags],
            overall_bias_risk=overall_bias_risk,
            audited_message_count=audited_message_count,
            flagged_message_count=flagged_message_count,
        )
        return result.model_dump()

    @staticmethod
    def _check_biased_language(responses: str) -> List[ChatbotBiasFlag]:
        """Scan tutor responses for known biased phrases and return flags."""
        flags: List[ChatbotBiasFlag] = []
        responses_lower = responses.lower()
        for phrase, alternative in _BIASED_PHRASES.items():
            if re.search(r'\b' + re.escape(phrase) + r'\b', responses_lower):
                flags.append(
                    ChatbotBiasFlag(
                        message_index=0,
                        bias_category=ChatbotBiasCategory.language_bias,
                        severity=ChatbotBiasSeverity.low,
                        explanation=(
                            f"The phrase \"{phrase}\" was detected in the tutor response. "
                            f"This may be considered non-inclusive language."
                        ),
                        suggestion=f"Consider replacing with \"{alternative}\".",
                    )
                )
        return flags

    @staticmethod
    def _check_patronizing_language(responses: str) -> List[ChatbotBiasFlag]:
        """Scan tutor responses for patronizing phrases and return flags."""
        flags: List[ChatbotBiasFlag] = []
        responses_lower = responses.lower()
        for phrase in _PATRONIZING_PHRASES:
            if phrase in responses_lower:
                flags.append(
                    ChatbotBiasFlag(
                        message_index=0,
                        bias_category=ChatbotBiasCategory.tone_bias,
                        severity=ChatbotBiasSeverity.medium,
                        explanation=(
                            f"The phrase \"{phrase}\" was detected in the tutor response. "
                            f"This may come across as patronizing or condescending."
                        ),
                        suggestion="Use encouraging language that respects the learner's effort and level.",
                    )
                )
        return flags

    @staticmethod
    def _count_tutor_messages(responses: str) -> int:
        """Estimate the number of tutor messages from the response text."""
        # Look for assistant/tutor message markers or count paragraphs
        markers = re.findall(r'(?:^|\n)(?:assistant|tutor|ami):', responses, re.IGNORECASE)
        if markers:
            return len(markers)
        # Fallback: treat as a single response
        return max(1, len(responses.strip().split('\n\n')))


def audit_chatbot_bias_with_llm(
    llm: Any,
    tutor_responses: str,
    learner_information: str,
) -> JSONDict:
    """Convenience function: create a ChatbotBiasAuditor and run the audit."""
    auditor = ChatbotBiasAuditor(llm)
    return auditor.audit_responses({
        "tutor_responses": tutor_responses,
        "learner_information": learner_information,
    })
