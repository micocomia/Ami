## Revised Plan: Refactor + One-Call Content API + `ami` Standard + Mini-LLM Routing

### Summary
Refactor content generation into orchestrator architecture, switch frontend to one call, standardize method name to `ami` throughout defaults/configs, and formalize lightweight `gpt-4o-mini` usage for applicable non-core tasks.

### 1. Endpoint and API Decisions
1. Add `POST /generate-learning-content` in [main.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/main.py).
2. Remove these endpoints (the 4-step flow + old single-call route):
   - `/explore-knowledge-points`
   - `/draft-knowledge-points`
   - `/integrate-learning-document`
   - `/generate-document-quizzes`
   - `/tailor-knowledge-content`
3. Keep `/draft-knowledge-point` for eval/debug use (not part of the deprecated 4-step frontend path).
4. Response from `/generate-learning-content` is final payload only: `document`, `quizzes`, `sources_used`, `content_format`, `audio_url`, `audio_mode`, `inline_assets_count`, `inline_assets_placement_stats`.

### 2. Method Name Standardization (`ami`)
1. Set `BaseRequest.method_name = "ami"` in [api_schemas.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/api_schemas.py).
2. Set backend config default `default_method_name: "ami"` in [main.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/main.py).
3. Set frontend fallback default `default_method_name: "ami"` in [request_api.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/frontend/utils/request_api.py).
4. Replace explicit `"genmentor"` defaults/usages in frontend/backend callsites (for example [gap_identification.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/frontend/components/gap_identification.py)).
5. Enforce `method_name == "ami"` for `/generate-learning-content`; return `400` otherwise.

### 3. Backend Refactor Structure
1. Create orchestrator entrypoint in [content_generation_pipeline.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/modules/content_generator/orchestrators/content_generation_pipeline.py):
   - `generate_learning_content_with_llm(...)`
   - owns explore → draft → media/narrative → integrate → quiz.
2. Keep [learning_content_creator.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/modules/content_generator/agents/learning_content_creator.py) agent-scoped; move orchestration out.
3. Add `utils` modules:
   - [fslsm_adaptation.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/modules/content_generator/utils/fslsm_adaptation.py)
   - [sources.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/modules/content_generator/utils/sources.py)
   - [model_routing.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/modules/content_generator/utils/model_routing.py)
4. Move tool-like helpers to utils but keep compatibility shims:
   - utils canonical modules for media finder + tts
   - agent-path wrappers at existing locations to avoid immediate import/test breakage.
5. Export orchestrator in:
   - [orchestrators/__init__.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/modules/content_generator/orchestrators/__init__.py)
   - [content_generator/__init__.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/modules/content_generator/__init__.py)

### 4. Lightweight LLM (`gpt-4o-mini`) Policy
1. Add centralized helper in `model_routing.py` to get `lightweight_llm` with fallback to `primary_llm`.
2. Use primary model for content-quality-critical generation:
   - exploration, drafting, integration, quizzes, podcast conversion.
3. Use lightweight model for applicable support tasks:
   - media relevance evaluation
   - narrative TTS normalization
   - future evaluator hook.
4. Refactor support helpers to accept optional `lightweight_llm` so they do not each re-create mini independently.
5. Fallback rule: mini failure never fails pipeline; retry that step with primary model.

### 5. Frontend One-Call Migration
1. Add `generate_learning_content(...)` wrapper in [request_api.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/frontend/utils/request_api.py) to call `/generate-learning-content`.
2. Remove staged content wrappers from content page usage.
3. Update [knowledge_document.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/frontend/pages/knowledge_document.py):
   - one spinner only
   - one backend call
   - cache final payload directly
   - render citations from backend `sources_used`.

### 6. Evals, Docs, and Tooling Updates (Gap Fix)
1. Update eval scripts that currently call removed endpoints:
   - [eval_content.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/evals/eval_content.py)
   - [eval_api_perf.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/evals/eval_api_perf.py)
   - [evaluation_guide.md](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/evals/evaluation_guide.md)
2. Keep any per-KP micro-eval paths on `/draft-knowledge-point` until a dedicated internal eval interface is added.
3. Update curl/docs in [backend/README.md](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/README.md).

### 7. Tests and Acceptance
1. Update endpoint tests in [test_goal_context_plumbing.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/tests/test_goal_context_plumbing.py):
   - new endpoint success
   - removed endpoints return 404
   - `/draft-knowledge-point` still reachable.
2. Update orchestrator/import tests in [test_adaptive_content_delivery.py](/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/tests/test_adaptive_content_delivery.py).
3. Add mini-routing tests:
   - mini used for support steps
   - fallback to primary when mini unavailable.
4. Frontend acceptance:
   - exactly one content-generation API call
   - document/quiz/audio/citation parity with previous behavior.

### Assumptions
1. `ami` is the only accepted method for the new content generation endpoint.
2. Hard deprecation applies to the 4-step frontend content path endpoints and old tailored route.
3. `/draft-knowledge-point` remains intentionally available for eval/debug continuity.
