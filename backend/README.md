# Backend of Ami

Ami's backend is a FastAPI service that powers authentication, learner/profile persistence, skill-gap analysis with bias auditing, adaptive learning-path generation, multi-modal content generation with quality gates, session prefetch, runtime orchestration, and analytics.

It is designed to work with the Streamlit frontend in `../frontend`, but can also be used directly through the API.

## What This Backend Provides

- **Authentication and accounts** (`/auth/*`)
- **Goal lifecycle and multi-goal state** (`/goals/*`)
- **Learner profile creation, update, and sync** (`/profile/*`, `/sync-profile/*`) — FSLSM dimensions and learner information are updated via separate scoped endpoints
- **Skill-gap analysis with two-loop reflexion and bias auditing** — ethics/bias checks run across all major surfaces: skill gaps (`BiasAuditor`), learner profiles (`FairnessValidator`), generated content (`ContentBiasAuditor`), and chatbot responses (`ChatbotBiasAuditor`)
- **Learning-path scheduling and agentic adaptation** with embedded plan feedback simulation
- **Content generation** — staged quality pipeline with evaluators, FSLSM-aware adaptation, and multi-modal enrichment (audio/TTS, media search, diagrams)
- **Session content caching and prefetch** (`services/content_prefetch.py`)
- **Session activity tracking and mastery evaluation**
- **Behavioral and dashboard analytics**

## Architecture Overview

### Core entry points

- `main.py`: FastAPI app and endpoint orchestration
- `api_schemas.py`: request/response Pydantic schema classes
- `config/`: Hydra configuration

### Main module packages

- `modules/skill_gap/`
- `modules/learner_profiler/`
- `modules/learning_plan_generator/`
- `modules/content_generator/`
- `modules/ai_chatbot_tutor/`

### Supporting services/utilities

- `services/content_prefetch.py`: background prefetch of upcoming sessions while learner is in current session (single-flight coordination, configurable concurrency)
- `base/llm_factory.py`: model client initialization for multiple providers
- `base/search_rag.py`: retrieval and verified-content integration via Azure AI Search + web search runners
- `base/verified_content_manager.py` + `base/verified_content_loader.py`: indexes PDFs/slides from `resources/verified-course-content/` into Azure AI Search; uses blob-backed manifests to avoid unnecessary re-indexing
- `base/blob_storage.py`: Azure Blob Storage access for manifests, generated audio, diagrams, and course-content blobs
- `base/cosmos_client.py`, `utils/store.py`, `utils/auth_store.py`: Azure Cosmos DB-backed runtime persistence for users, goals, profiles, events, auth state, and cached learning content
- `utils/auth_jwt.py`: JWT token handling
- `utils/solo_evaluator.py`: SOLO Taxonomy rubric-based quiz assessment
- `utils/quiz_scorer.py`: quiz evaluation logic

## Key Module Architecture

### Cross-cutting quality and bias auditing

Quality control and safety checks are implemented across multiple backend surfaces, not just inside a single generation flow:

| Surface | Agent / mechanism | What it checks |
|---|---|---|
| Skill gap | `BiasAuditor` | Demographic or confidence-level bias in gap assumptions |
| Learner profile | `FairnessValidator` | Stereotyping or demographic bias in profile construction |
| Learning plans | `LearningPlanFeedbackSimulator` | Plan quality, pacing, and refinement directives before the plan is accepted |
| Draft content | deterministic draft audits + `KnowledgeDraftEvaluator` | Draft quality, instructional coverage, and targeted repair directives |
| Integrated content | `IntegratedDocumentEvaluator` | Full-document quality, repair scope (`integrator_only` / `section_redraft`), and fallback behavior |
| Generated content | `ContentBiasAuditor` | Exclusionary framing, inappropriate language, or demographic bias in lesson material |
| Chatbot responses | `ChatbotBiasAuditor` | Bias or inappropriate content in tutor replies |

### `skill_gap` module

Primary orchestration entrypoint: `identify_skill_gap_with_llm`

- Runs an explicit two-loop reflexion flow:
  - Loop 1: `GoalContextParser` and `LearningGoalRefiner` (goal clarification only)
  - Between loops: verified-content retrieval and `SkillRequirementMapper` run against the finalized goal when goal context supports retrieval
  - Loop 2: `SkillGapIdentifier` and `SkillGapEvaluator` (skill-gap critique/refinement only)
- Computes top-level `goal_assessment`, `goal_context`, and `retrieved_sources`
- Always executes `BiasAuditor` post-loop as a mandatory ethics gate — checks for demographic or confidence-level bias in skill gap assumptions

### `learner_profiler` module

Primary agent: `AdaptiveLearningProfiler`

The learner profile evolves throughout the lifecycle via four update channels:

- **Manual edit** (user-initiated): `update_learning_preferences_with_llm` (FSLSM sliders) and `update_learner_information_with_llm` (background/bio + optional resume) — scoped separately to prevent cross-field changes
- **Event-driven profile updates** (runtime-driven): `auto_update_learner_profile` can initialize or refresh the learner profile from persisted behavioral events and session metadata
- **Quiz-driven cognitive progression** (automated): `update_cognitive_status_with_llm` — advances SOLO level based on mastery evaluation outcomes
- **Interaction-driven preference updates**: content feedback and `update_learning_preferences_from_signal` in `ai_chatbot_tutor` can update FSLSM preferences when strong evidence is present; persisted updates are guarded by bounded FSLSM deltas and sign-flip reset logic

Additional:
- `initialize_learner_profile_with_llm` — creates initial FSLSM + SOLO profile from persona and optional resume
- `update_learner_profile_with_llm` — full profile update
- `fslsm_adaptation.py` utility handles FSLSM vector updates and adaptation logic
- `FairnessValidator` agent validates profiles for bias

Downstream effect:
- updated learner state is consumed by learning-path generation, content generation, quiz/mastery flows, and tutor behavior so later sessions can adapt as the learner changes over time

### `learning_plan_generator` module

Primary orchestration entrypoint: `schedule_learning_path_agentic`

- Generates initial path with `LearningPathScheduler.schedule_session`
- Applies FSLSM structural overrides to scheduled/refined sessions
- Evaluates plan quality via embedded plan feedback simulator (`LearningPlanFeedbackSimulator`)
- Carries `generation_observations` into the feedback loop for plan critique
- Uses `LearningPathScheduler.reflexion` with evaluator directives when quality threshold is not met
- Returns both `learning_path` and iteration metadata

### `content_generator` module

Primary orchestration entrypoint: `generate_learning_content_with_llm`

Staged pipeline with embedded quality gates and optional enrichment branches:

1. **Knowledge exploration** — `GoalOrientedKnowledgeExplorer` identifies key concepts for the goal
2. **Draft generation** — `SearchEnhancedKnowledgeDrafter` drafts knowledge points using RAG + web search
3. **Draft reflexion loop** — deterministic audits + `KnowledgeDraftEvaluator` (LLM) evaluate each draft; failed sections undergo targeted repair before proceeding
4. **Media / narrative enrichment** — optional media retrieval/filtering and narrative generation run when the learner profile calls for them
5. **Integration** — `LearningDocumentIntegrator` merges all components into a coherent document
6. **Integration reflexion loop** — `IntegratedDocumentEvaluator` evaluates the full document; targeted repair (`integrator_only`, `section_redraft`) runs on failure; fallback path when quality budget is exhausted
7. **Optional audio + quiz** — podcast/narration conversion, TTS generation, and SOLO-aligned quiz generation run when applicable

Additional capabilities:
- **FSLSM-aware adaptation** (`fslsm_adaptation.py`): tailors content format and style to learner's FSLSM profile
- **Media enrichment**: `MediaResourceFinder` + `MediaRelevanceEvaluator` for external videos/diagrams/podcasts; `DiagramRenderer` for rendered diagrams; `TTSGenerator` for audio
- **Quiz generation**: `DocumentQuizGenerator` produces SOLO-aligned quizzes
- **Bias auditing**: `ContentBiasAuditor` checks generated lesson material for exclusionary framing, inappropriate language, or demographic bias

### `ai_chatbot_tutor` module

Runtime tool-fetching entrypoints:
- `AITutorChatbot._build_runtime_tools`
- `create_ai_tutor_tools`

Per-request tool assembly; each tool can be individually enabled/disabled:

| Tool | Purpose |
|---|---|
| `retrieve_session_learning_content` | Access current session's learning document |
| `retrieve_vector_context` | Verified-content RAG from indexed course materials |
| `search_web_context_ephemeral` | Ephemeral web search (non-persistent) |
| `search_media_resources` | Search and filter media resources |
| `update_learning_preferences_from_signal` | Signal-gated FSLSM profile updates |

Preference updates are signal-gated: profile writes occur only when strong preference signals are detected and user/goal context is present. Tool availability is assembled per request, with toggles for vector retrieval, web search, media search, and preference updates.

`ChatbotBiasAuditor` can be run post-response to check tutor replies for bias or inappropriate content (exposed via `/audit-chatbot-bias`).

## Quickstart

### Option A: Docker (Recommended)

Docker runs the backend in an isolated container so you do not need to manage local Python dependencies.

#### Step 1 — Install Docker Desktop

Download and install Docker Desktop for your OS:

| Operating System | Download Link |
|---|---|
| Windows 10/11 | [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) |
| macOS (Intel / Apple Silicon) | [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) |
| Linux | [Docker Desktop for Linux](https://docs.docker.com/desktop/setup/install/linux/) |

After installation, open Docker Desktop and wait until it is fully started.

#### Step 2 — Open a Terminal and Enter the Backend Folder

```bash
cd path/to/Ami/backend
```

Replace `path/to/Ami` with your local path.

#### Step 3 — Prepare `.env`

```bash
cp .env.example .env
```

Open `.env` and fill in the keys required by the current backend stack:

- `OPENAI_API_KEY`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_KEY`
- `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_COSMOS_CONNECTION_STRING`
- `JWT_SECRET`

Also set `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` and `AZURE_DOCUMENT_INTELLIGENCE_KEY` if you plan to ingest or re-index verified course content from PDFs or slides.

#### Step 4 — Build and Start Backend Container

```bash
docker compose -f docker/docker-compose.yml up --build
```

First run may take several minutes while Docker downloads base images and dependencies.

#### Step 5 — Open the API

- API base: `http://localhost:8000`
- API docs (Swagger UI): `http://localhost:8000/docs`

#### Stopping / Restarting

Stop:

```bash
docker compose -f docker/docker-compose.yml down
```

Restart:

```bash
docker compose -f docker/docker-compose.yml up
```

Rebuild after dependency/code changes:

```bash
docker compose -f docker/docker-compose.yml up --build
```

#### Docker notes

- Compose maps host `8000` to container `8000`.
- Compose mounts `../data` → `/app/data` and `../resources` → `/app/resources`.
- Data persists across container restarts through the mounted directories.

### Option B: Local Python (venv)

#### Prerequisites

- Python 3.13
- `pip`

#### Cross-Platform Notes (Windows / macOS / Linux)

All dependencies in `requirements.txt` are cross-platform compatible. Key details:

| Package | Notes |
|---|---|
| `torch`, `torchvision` | CPU wheels from PyPI work on Windows, macOS (Intel + Apple Silicon), and Linux. No extra index URL needed. |
| `opencv-python-headless` | Headless variant — no system GUI libraries required. Works identically on all platforms. |
| `onnxruntime` | Pre-built wheels available for Windows, macOS, and Linux. |
| `pyclipper`, `grpcio`, `brotli` | C extensions with pre-built wheels for all major platforms. |
| `rapidocr` | Depends on `onnxruntime`; works wherever onnxruntime works. |

**Windows-specific:** Use `python -m venv .venv` then `.venv\Scripts\activate` (backslash, no `source`).

**macOS Apple Silicon:** If `pip install` fails for any native package, ensure you are using a native ARM Python (not Rosetta). Run `python -c "import platform; print(platform.machine())"` — should print `arm64`.

#### Step 1 — Install dependencies

From repo root:

```bash
python -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate        # Windows
pip install -r backend/requirements.txt
```

#### Step 2 — Configure env

```bash
cp backend/.env.example backend/.env
```

Fill the same required backend keys listed above in `backend/.env`.

#### Step 3 — Start backend

Recommended (for frontend compatibility):

```bash
./scripts/start_backend.sh 8000
```

Alternative direct run from `backend/`:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Option C: Local Python (Conda)

```bash
conda create -n ami-backend python=3.13 -y
conda activate ami-backend
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
./scripts/start_backend.sh 8000
```

## Ports and Startup Behavior

Important current defaults:

- Docker backend: **8000**
- `./scripts/start_backend.sh` default: **5000** if no argument and no `BACKEND_PORT`

For default frontend behavior, run backend on **8000**:

```bash
./scripts/start_backend.sh 8000
# or
BACKEND_PORT=8000 ./scripts/start_backend.sh
```

## Environment Variables

`backend/.env.example` currently includes:

```bash
TOGETHER_API_KEY=...
DEEPSEEK_API_KEY=...
OPENAI_API_KEY=...

SERPER_API_KEY=...
BING_SUBSCRIPTION_KEY=...
BING_SEARCH_URL=...
BRAVE_API_KEY=...

USER_AGENT=Ami/1.0 (educational-platform)

AZURE_SEARCH_ENDPOINT=https://<your-service-name>.search.windows.net
AZURE_SEARCH_KEY=<your-admin-key>

AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=<your-key>

AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...

AZURE_COSMOS_CONNECTION_STRING=AccountEndpoint=https://<your-account>.documents.azure.com:443/;AccountKey=<your-key>==;

JWT_SECRET=change-me-to-a-random-string-in-production
```

Guidance:

- Set at least one working LLM key.
- `AZURE_SEARCH_ENDPOINT` and `AZURE_SEARCH_KEY` are required for the Azure AI Search-backed vector indexes used by verified-content retrieval and shared web-result caching.
- `AZURE_STORAGE_CONNECTION_STRING` is required for blob-backed manifests and generated media assets.
- `AZURE_COSMOS_CONNECTION_STRING` is required for persisted runtime/user data.
- `AZURE_DOCUMENT_INTELLIGENCE_*` is required when extracting/indexing verified source documents from PDFs or slides.
- Keep `JWT_SECRET` strong and private.
- Search provider keys are needed only if you use those providers.

## Configuration (Hydra)

Backend config files:

- `config/main.yaml`
- `config/default.yaml`

Current repo defaults include:

- `llm.provider: openai`
- `llm.model_name: gpt-4o`
- `embedding.provider: openai`
- `embedding.model_name: text-embedding-3-small`
- `search.provider: duckduckgo`
- `vectorstore.type: azure_ai_search`
- `vectorstore.collection_name: ami-web-results`
- `azure_search.verified_index_name: ami-verified-content`
- `blob_storage.course_content_container: ami-course-content`
- `cosmos.database_name: ami-userdata`
- `verified_content.enabled: true`
- `prefetch.enabled: true` (configures background session prefetch)

The backend also exposes runtime config via:

- `GET /config`

## Request Interface Notes

Many generation/profile endpoints share a base schema that accepts optional model overrides:

- `model_provider`
- `model_name`

If omitted, backend uses configured defaults.

`/chat-with-tutor` also supports additive optional request controls:

- retrieval/search/media toggles (`use_vector_retrieval`, `use_web_search`, `use_media_search`)
- preference-update toggle (`allow_preference_updates`)
- contextual identifiers (`user_id`, `goal_id`, `session_index`)
- `return_metadata` mode for structured tutor responses (`response`, `profile_updated`, optional updated profile payload)

## Interactive API Documentation

The backend exposes a full Swagger UI at runtime:

- **Swagger UI**: `http://localhost:8000/docs`
- **OpenAPI schema**: `http://localhost:8000/openapi.json`

All endpoints are listed and can be tested directly from the browser. Endpoints are split into **Public** (no auth required) and **Protected** (requires `Authorization: Bearer <token>` header) sections.

![FastAPI endpoint documentation](assets/fastapi_endpoints.png)

## API Endpoint Map

### Auth

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `DELETE /auth/user`

### Goals and Profiles

- `GET /goals/{user_id}`
- `POST /goals/{user_id}`
- `PATCH /goals/{user_id}/{goal_id}`
- `DELETE /goals/{user_id}/{goal_id}`
- `GET /profile/{user_id}`
- `PUT /profile/{user_id}/{goal_id}`
- `POST /sync-profile/{user_id}/{goal_id}`
- `POST /propagate-profile/{user_id}/{goal_id}`
- `POST /profile/auto-update`

### Runtime and Content

- `GET /goal-runtime-state/{user_id}`
- `GET /learning-content/{user_id}/{goal_id}/{session_index}`
- `DELETE /learning-content/{user_id}/{goal_id}/{session_index}`
- `POST /session-activity`
- `POST /complete-session`
- `POST /submit-content-feedback`

### Generation and Planning

- `POST /chat-with-tutor`
- `POST /refine-learning-goal`
- `POST /identify-skill-gap-with-info`
- `POST /audit-skill-gap-bias`
- `POST /create-learner-profile-with-info`
- `POST /validate-profile-fairness`
- `POST /update-learner-profile`
- `POST /update-cognitive-status`
- `POST /update-learning-preferences`
- `POST /update-learner-information`
- `POST /schedule-learning-path`
- `POST /schedule-learning-path-agentic`
- `POST /adapt-learning-path`
- `POST /draft-knowledge-point`
- `POST /generate-learning-content`
- `POST /simulate-content-feedback`

### Analytics and Assessment

- `GET /dashboard-metrics/{user_id}`
- `GET /behavioral-metrics/{user_id}`
- `GET /quiz-mix/{user_id}`
- `GET /session-mastery-status/{user_id}`
- `POST /evaluate-mastery`

### Utility and Ops

- `GET /config`
- `GET /personas`
- `GET /list-llm-models`
- `POST /extract-pdf-text`
- `POST /events/log`
- `GET /events/{user_id}`
- `DELETE /user-data/{user_id}`

## Example API Calls

### Chat with tutor

```bash
curl -X POST "http://localhost:8000/v1/chat-with-tutor" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "messages": "[{\"role\":\"user\",\"content\":\"Help me learn recursion\"}]",
    "learner_profile": "{}",
    "model_provider": "openai",
    "model_name": "gpt-4o"
  }'
```

### Agentic schedule learning path

```bash
curl -X POST "http://localhost:8000/v1/schedule-learning-path-agentic" \
  -H "Content-Type: application/json" \
  -d '{
    "learner_profile": "{\"learning_goal\":\"Learn Python\"}",
    "session_count": 8,
    "model_provider": "openai",
    "model_name": "gpt-4o"
  }'
```

## Persistence and Data Paths

Backend-managed runtime persistence now uses Azure services:

- **Azure Cosmos DB**
  - users, goals, profiles, events, session activity, mastery history, auth state, cached learning content
- **Azure AI Search**
  - `ami-web-results`: shared web-search cache / general retrieval index
  - `ami-verified-content`: verified course-content index
- **Azure Blob Storage**
  - verified-content sync manifests
  - generated audio and diagrams
  - course-content source files when using blob-backed indexing flows

Local paths still used during development/testing:

- `backend/resources/verified-course-content/`
  - local verified source corpus used by indexing and sync flows
- `backend/data/`
  - transient local artifacts used by some scripts/tests and compatibility paths

## Project Structure (Backend)

```text
backend/
  main.py
  api_schemas.py
  requirements.txt

  config/
    main.yaml
    default.yaml
    loader.py
    schemas.py

  base/
    base_agent.py
    dataclass.py
    llm_factory.py
    rag_factory.py
    embedder_factory.py
    searcher_factory.py
    search_rag.py
    verified_content_manager.py
    verified_content_loader.py

  services/
    content_prefetch.py

  modules/
    ai_chatbot_tutor/
    skill_gap/
    learner_profiler/
    learning_plan_generator/
    content_generator/

  utils/
    store.py
    auth_store.py
    auth_jwt.py
    solo_evaluator.py
    quiz_scorer.py
    llm_output.py

  evals/
  tests/
  docker/
```

## Testing

From `backend/`:

```bash
python -m pytest tests
```

Most tests mock LLM calls via `unittest.mock`, and many suites run without external services. Some integration-style paths depend on configured Azure/search services unless explicitly mocked. Tests use FastAPI's `TestClient`.

## Common Dev Commands

From repo root:

```bash
# backend only (foreground)
./scripts/start_backend.sh 8000

# backend + frontend (background with pid/log files)
BACKEND_PORT=8000 ./scripts/start_all.sh

# stop both when started by start_all.sh
./scripts/stop_all.sh
```

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `docker: command not found` | Docker missing / PATH issue | Install Docker Desktop and restart terminal |
| `Cannot connect to Docker daemon` | Docker not running | Start Docker Desktop fully |
| Port `8000` already in use | Another process is bound | Stop that process or map a different host port |
| Frontend cannot call backend | Backend running on `5000` via script default | Start backend with `./scripts/start_backend.sh 8000` |
| 401 responses | Missing/invalid token | Use `/auth/login` and send `Authorization: Bearer <token>` |
| Model/provider call errors | Missing API key or wrong provider/model | Verify `.env` keys and request `model_provider`/`model_name` |
| No media URLs working | Data directories unavailable | Check `backend/data/audio` and `backend/data/diagrams` write access |
| Sparse/empty analytics | Insufficient runtime events/sessions | Exercise session endpoints and complete sessions first |

## License

This project is released under the repository's top-level license.
