## Ami Tutor Upgrade Plan (Revised, Gap-Closed)

### Summary
Upgrade `ai_chatbot_tutor` into a tool-enabled “Ami” mentor with five capabilities: session-content grounding, vector retrieval, web search fallback, media search, and preference adaptation.  
This revision closes identified risks: adaptation safety, wrong session targeting, vectorstore contamination, context/token bloat, flaky tests, and response compatibility breaks.

### Implementation plan

1. Create tutor-specific tools with strict boundaries in [backend/modules/tools/ai_tutor_tools.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/tools/ai_tutor_tools.py).  
Tools: `retrieve_session_learning_content`, `retrieve_vector_context`, `search_web_context_ephemeral`, `search_media_resources`, `update_learning_preferences_from_signal`.

2. Implement a shared safe preference-update helper in backend runtime path, then reuse it from both `/submit-content-feedback` and tutor tool paths in [backend/main.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/main.py).  
Behavior: snapshot old profile, update preferences with LLM, run sign-flip reset, persist profile, return `{updated_profile, profile_updated}`.

3. Add explicit signal-gating for preference updates inside tutor tools.  
Default policy: only strong cues trigger persistence (e.g., “show me visual examples”, “less text”, “more step-by-step”); otherwise no profile write.

4. Build session-document retrieval with token budgeting.  
Current session first; if no hit, fallback to same-goal sessions. Return capped snippets (section-matched when possible), not full documents.

5. Use non-persistent web retrieval for tutor web-search tool.  
Do not call `SearchRagManager.invoke()` in tutor web tool. Use `search_runner.invoke()` + lightweight formatting only, so chat does not write web docs into shared vectorstore.

6. Keep vector retrieval tool strictly vector-only.  
Use `SearchRagManager.retrieve(query, k)` for existing persistent knowledge base retrieval.

7. Reuse content-generator media finder pipeline in tutor media tool.  
Use `find_media_resources` and optional `filter_media_resources_with_llm`; return normalized link payload for chat responses.

8. Refactor tutor agent orchestration in [backend/modules/ai_chatbot_tutor/agents/ai_chatbot_tutor.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/ai_chatbot_tutor/agents/ai_chatbot_tutor.py).  
Add payload fields: `user_id`, `goal_id`, `session_index`, `use_vector_retrieval`, `use_web_search`, `use_media_search`, `allow_preference_updates`, `top_k`, `return_metadata`, `learner_information`.  
Maintain backward compatibility: default return remains string unless `return_metadata=true`.

9. Update tutor prompt persona and tool policy in [backend/modules/ai_chatbot_tutor/prompts/ai_chatbot_tutor.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/ai_chatbot_tutor/prompts/ai_chatbot_tutor.py).  
Persona: “Ami.”  
Tool order: session content first for clarification; vector retrieval second; web fallback only when needed; media tool when requested; preference-update tool only on strong signal.

10. Extend request schema additively in [backend/api_schemas.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/api_schemas.py).  
`ChatWithAutorRequest` gets optional context/toggles listed above; existing fields remain valid.

11. Update `/chat-with-tutor` endpoint in [backend/main.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/main.py).  
Pass optional fields through; if metadata mode enabled, return `{response, profile_updated, updated_learner_profile?}`; otherwise legacy `{response}`.

12. Make lightweight frontend payload updates in [frontend/utils/request_api.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/utils/request_api.py) and [frontend/components/chatbot.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/components/chatbot.py).  
Send `user_id`, `goal_id`; send `session_index` only when context is known valid; opt into metadata mode; if profile was updated, merge into selected goal state.

### Public API/interface changes

1. `POST /chat-with-tutor` request: additive optional fields only.  
No required-field changes.

2. `POST /chat-with-tutor` response: additive metadata mode.  
Legacy callers still receive and can consume `response` exactly as today.

3. Python helper `chat_with_tutor_with_llm(...)`: backward-compatible default string return; opt-in structured metadata return.

### Testing plan

1. Add `backend/tests/test_ai_chatbot_tutor_tools.py`.  
Cases: current-session-first retrieval, fallback retrieval, vector-only retrieval, non-persistent web retrieval, media tool normalization, preference signal gate on/off, safe update path invoked.

2. Add/extend endpoint tests in backend API test suite.  
Cases: legacy request/response compatibility; metadata mode includes profile updates; invalid message format still 400.

3. Add regression test for adaptation safety.  
Verify tutor-triggered preference update uses snapshot + sign-flip reset semantics and persists expected profile.

4. Ensure deterministic tests by mocking all network-facing dependencies.  
Mock `search_runner.invoke`, `requests.get` (Wikimedia), and optional media relevance LLM calls.

### Edge cases and failure handling

1. Missing `user_id/goal_id`: tutor still replies; context/profile-write tools no-op safely.  
2. Missing/invalid `session_index`: backend falls back to goal-wide retrieval without mis-targeting session 0 by default.  
3. Tool errors/timeouts: fallback to plain Ami response without crashing endpoint.  
4. Oversized context: enforce snippet caps and `top_k` limits.

### Acceptance criteria

1. Ami can clarify questions using generated session content from `learning_content.json`.  
2. Ami can retrieve internal vector context and only uses web search as fallback.  
3. Ami can return relevant media links using existing media search pipeline.  
4. Strong preference signals persist profile updates safely and are reflected in subsequent interactions.  
5. Existing `/chat-with-tutor` consumers continue to work unchanged.

### Assumptions and defaults

1. Preference auto-update policy is signal-based only.  
2. Session retrieval scope is current session first, then all goal sessions.  
3. Streamlit receives lightweight compatibility updates now; React migration can reuse same optional contract later.  
4. No data migration is required for existing store files.
