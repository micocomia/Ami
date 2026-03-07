# AI Chatbot Tutor Bias Auditor — Implementation Plan

## Context
The project already has 3 bias auditors (Skill Gap, Learner Profiler, Content Generator). The AI Chatbot Tutor is the last directly learner-facing module without bias auditing. Since it generates free-form conversational responses, it can introduce bias independently of the other audited modules. This implementation follows the exact same hybrid (LLM + deterministic) pattern established by the existing auditors.

## Files to Create

### 1. `backend/modules/ai_chatbot_tutor/schemas.py`
New schemas file with:
- `ChatbotBiasCategory` enum: `tone_bias`, `language_bias`, `stereotype_bias`, `cultural_assumption`
- `ChatbotBiasSeverity` enum: `low`, `medium`, `high`
- `ChatbotBiasFlag` model: with `message_index`, `bias_category`, `severity`, `explanation` (max 40 words), `suggestion` (max 30 words)
- `ChatbotBiasAuditResult` model: `bias_flags`, `deterministic_flags`, `overall_bias_risk`, `audited_message_count`, `flagged_message_count`, `ethical_disclaimer`

### 2. `backend/modules/ai_chatbot_tutor/prompts/chatbot_bias_auditor.py`
System prompt instructing the LLM to audit chatbot responses for:
- **Tone bias**: condescending, patronizing, or overly simplified responses based on learner demographics
- **Language bias**: gendered, ableist, or culturally insensitive phrasing
- **Stereotype bias**: adjusting explanation depth/style based on demographic assumptions rather than assessed skill level
- **Cultural assumptions**: examples or analogies that assume a specific cultural context

Task prompt accepting `tutor_responses` and `learner_information`.

### 3. `backend/modules/ai_chatbot_tutor/agents/chatbot_bias_auditor.py`
- `ChatbotBiasAuditPayload` pydantic model (tutor_responses: str, learner_information: str)
- `ChatbotBiasAuditor(BaseAgent)` class with `audit_responses()` method
- Deterministic checks: reuse the same `_BIASED_PHRASES` dict pattern (biased language scanning)
- Additional deterministic check: detect patronizing phrases (e.g., "as I'm sure you know", "this is really simple", "obviously", "even you can")
- Risk promotion: if deterministic flags exist but LLM said "low", promote to "medium"
- `audit_chatbot_bias_with_llm()` convenience function

### 4. `backend/tests/test_chatbot_bias_auditor.py`
Following the content bias auditor test pattern:
- `TestChatbotBiasAuditSchemas` — validate enums and models
- `TestBiasedLanguageCheck` — deterministic phrase detection
- `TestPatronizingPhraseCheck` — patronizing language detection
- `TestChatbotBiasAuditorAgent` — agent with mocked LLM
- `TestAuditChatbotBiasWithLlm` — convenience function

### 5. `frontend/components/chatbot_bias.py`
`render_chatbot_bias_banners(audit_result)` component — same pattern as `content_bias.py` with disclaimer, risk warning, and expandable details.

## Files to Modify

### 6. `backend/api_schemas.py`
Add `ChatbotBiasAuditRequest(BaseRequest)` with fields: `tutor_responses: str`, `learner_information: str`

### 7. `backend/main.py`
- Import `audit_chatbot_bias_with_llm` from the chatbot module
- Add `POST /audit-chatbot-bias` endpoint (same pattern as `/audit-content-bias`)

### 8. `backend/modules/ai_chatbot_tutor/__init__.py`
Add exports: `ChatbotBiasAuditor`, `audit_chatbot_bias_with_llm`

### 9. `backend/modules/ai_chatbot_tutor/prompts/__init__.py`
Create file exporting chatbot bias auditor prompts.

### 10. `frontend/utils/request_api.py`
Add `audit_chatbot_bias()` function and `"audit_chatbot_bias"` to `API_NAMES`

### 11. `frontend/components/chatbot.py`
After receiving the tutor response (line 56), call `audit_chatbot_bias()` non-blocking and render bias banners in the chat dialog if flags are detected.

## Verification
1. Run backend tests: `python -m pytest backend/tests/test_chatbot_bias_auditor.py -v`
2. Start backend and test endpoint: `curl -X POST http://localhost:8000/audit-chatbot-bias`
3. Start frontend, open chatbot, send a message, verify bias audit runs and banners render when appropriate
