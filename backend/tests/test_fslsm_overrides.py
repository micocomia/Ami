"""FSLSM override tests — superseded.

The deterministic `_apply_fslsm_overrides` post-processing function has been
removed. FSLSM structural fields (has_checkpoint_challenges, navigation_mode,
session_sequence_hint, thinking_time_buffer_minutes) are now set proportionally
by the Learning Path Scheduler LLM based on proportional magnitude guidance in
the system prompt.

End-to-end verification of FSLSM alignment is covered by:
- Manual/integration testing of POST /schedule-learning-path-agentic
- Plan quality assessor (LearnerPlanFeedbackSimulator) which checks FSLSM
  alignment and sets is_acceptable=False when misaligned

Run from the repo root:
    python -m pytest backend/tests/test_fslsm_overrides.py -v
"""

import pytest


class TestFSLSMPromptGuidance:

    def test_placeholder(self):
        """Placeholder — FSLSM overrides moved to LLM prompt guidance."""
        pass
