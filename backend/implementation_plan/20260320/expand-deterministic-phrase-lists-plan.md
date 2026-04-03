# Expand Deterministic Phrase Lists for Bias Detection

**Date:** 2026-03-20
**Branch:** sprint-7-bias-ethics-enhancement

## Context
The bias auditing system uses deterministic phrase lists alongside LLM-based analysis. The current lists are functional but limited. Expanding them improves detection coverage for non-inclusive, patronizing, and stereotypical language without relying solely on the LLM.

There are **4 phrase lists across 3 files** to expand.

## Files to Modify

### 1. `backend/modules/content_generator/agents/content_bias_auditor.py`
**`_BIASED_PHRASES` dict** (currently 15 entries) — add ~15 new inclusive language replacements:
- Gendered job titles: `businessman` → `businessperson`, `cameraman` → `camera operator`, `mailman` → `mail carrier`, `spokesman` → `spokesperson`, `housewife` → `homemaker`, `manpower` → `workforce`
- Ableist language: `crippled` → `disabled`, `lame` → `inadequate`, `blind spot` → `oversight`, `tone deaf` → `insensitive`, `crazy` → `unexpected`, `dumb` → `uninformed`
- Cultural/racial: `blacklist` → `blocklist`, `whitelist` → `allowlist`, `master/slave` → `primary/replica`

### 2. `backend/modules/ai_chatbot_tutor/agents/chatbot_bias_auditor.py`
**`_BIASED_PHRASES` dict** — mirror the same additions as file #1 (keep the two dictionaries in sync)

**`_PATRONIZING_PHRASES` list** (currently 14 entries) — add ~10 new patronizing patterns:
- `"let me dumb it down"`, `"i'll make it simple for you"`, `"you probably don't understand"`, `"just think about it"`, `"that's a basic concept"`, `"this is trivial"`, `"as i already explained"`, `"you're overthinking this"`, `"it's common sense"`, `"even a child could"`, `"surely you can see"`

### 3. `backend/modules/learner_profiler/agents/fairness_validator.py`
**`_STEREOTYPE_PHRASES` list** (currently 10 entries) — add ~8 new stereotype patterns:
- `"for someone like you"`, `"your kind of"`, `"not typical for"`, `"despite being"`, `"for your level"`, `"as a young person"`, `"as an older person"`, `"culturally speaking"`

## Verification
- Run existing tests: `pytest backend/tests/test_content_bias_auditor.py backend/tests/test_chatbot_bias_auditor.py backend/tests/test_fairness_validator.py`
- Verify the two `_BIASED_PHRASES` dicts stay in sync
