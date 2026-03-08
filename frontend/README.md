# Frontend of Ami

A Streamlit-based UI for Ami that supports authentication, onboarding, skill-gap analysis, learning-path navigation, in-session learning documents with multi-modal content, learner profile management, and analytics dashboards.

This frontend talks to the FastAPI backend over HTTP and can also run in mock mode with local JSON fixtures.

> **Note:** Streamlit is the current frontend interface. A React SPA is under active development and planned for the Beta release (Mar 18, 2026), which will provide a more polished, production-grade learner experience.

## Current App Flow

The app is auth-gated and goal-aware:

1. Login / Register
2. Onboarding (persona selection → FSLSM profile inferred + goal + optional resume)
3. Skill Gap (two-loop reflexion + bias audit)
4. Goal Management / Learning Path
5. Resume Learning (knowledge document + audio + media + quizzes)
6. Learner Profile (separate edit flows for FSLSM learning style vs. personal/background information)
7. Analytics Dashboard

If the user already has goals, the app routes directly into post-onboarding pages after login.

## How Frontend Uses the Enhanced Backend Pipelines

The frontend pages are thin orchestration/UI layers on top of backend pipelines:

- **Onboarding + Skill Gap** call the reflexion-enabled skill-gap flow (`/identify-skill-gap-with-info`) that performs goal clarification, skill-gap critique, and mandatory bias audit.
- **Learning Path** uses agentic planning and adaptation endpoints (`/schedule-learning-path-agentic`, `/adapt-learning-path`) backed by embedded plan feedback simulation.
- **Resume Learning (Knowledge Document)** consumes `/generate-learning-content`, which runs the full backend quality pipeline (draft evaluation, FSLSM-aware adaptation, targeted repair) before returning document + quiz + audio + media payloads.
- **Session Prefetch**: `ContentPrefetchService` runs in the backend background; subsequent sessions are prefetched while the learner works through the current one, reducing transition wait times.
- **Chatbot** calls `/chat-with-tutor`, where the backend assembles runtime tools per request (session content retrieval, vector retrieval, web-ephemeral retrieval, media search, optional signal-gated FSLSM preference update).
- **Learner Profile** uses separate scoped update endpoints: `/update-learning-preferences` for FSLSM dimensions and `/update-learner-information` for personal/background details.

## Quickstart

### Option A: Docker (Recommended)

Docker runs the frontend in an isolated container so you do not need to manage local Python dependencies.

#### Step 1 — Install Docker Desktop

Download and install Docker Desktop for your OS:

| Operating System | Download Link |
|---|---|
| Windows 10/11 | [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) |
| macOS (Intel / Apple Silicon) | [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) |
| Linux | [Docker Desktop for Linux](https://docs.docker.com/desktop/setup/install/linux/) |

After installation, open Docker Desktop and wait until it is fully started.

#### Step 2 — Open a Terminal and Enter the Frontend Folder

```bash
cd path/to/Ami/frontend
```

Replace `path/to/Ami` with your local path.

#### Step 3 — Start the Backend (Recommended)

The frontend expects a running backend on port `8000`. Follow the setup instructions in [`backend/README.md`](../backend/README.md) to start it.

By default, frontend calls `http://127.0.0.1:8000/` (or Docker override; see below).

> You can still run frontend in mock mode with no backend by setting `use_mock_data=True` in `frontend/config.py`.

#### Step 4 — Build and Start Frontend Container

From `frontend/`:

```bash
docker compose -f docker/docker-compose.yml up --build
```

First run may take several minutes while Docker downloads base images and dependencies.

#### Step 5 — Open the App

Visit:

```text
http://localhost:8501
```

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

### Option B: Local Python Setup

#### Prerequisites

- Python 3.13
- `pip` (or conda)

#### Cross-Platform Notes (Windows / macOS / Linux)

All frontend dependencies are pure Python or have pre-built wheels for all platforms. No special setup is needed beyond a standard `pip install`.

**Windows-specific:** Use `.venv\Scripts\activate` instead of `source .venv/bin/activate`.

#### Local Setup (venv)

From repo root:

```bash
python -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate        # Windows
pip install -r frontend/requirements.txt
```

Start frontend (default port 8501):

```bash
./scripts/start_frontend.sh
```

Or direct from `frontend/`:

```bash
streamlit run main.py
```

Run on a custom frontend port:

```bash
./scripts/start_frontend.sh 8600
# or
FRONTEND_PORT=8600 ./scripts/start_frontend.sh
```

#### Local Setup (Conda Alternative)

```bash
conda create -n ami-frontend python=3.13 -y
conda activate ami-frontend
pip install -r frontend/requirements.txt
./scripts/start_frontend.sh
```

## Backend Connection Behavior

Frontend resolves backend URLs through `frontend/config.py` and environment variables.

- `BACKEND_ENDPOINT`
  - API base URL used for HTTP calls from `utils/request_api.py`
  - default: `http://127.0.0.1:8000/`
- `BACKEND_PUBLIC_ENDPOINT`
  - browser-facing backend base for rendered media URLs (audio/diagrams)
  - default: derived from backend endpoint (for Docker, resolves to localhost-friendly URL)

### Docker Defaults

`frontend/docker/docker-compose.yml` sets:

```yaml
environment:
  - BACKEND_ENDPOINT=http://host.docker.internal:8000/
  - BACKEND_PUBLIC_ENDPOINT=http://localhost:8000/
```

### When to Change These

- Backend running on a non-default host/port.
- Remote backend deployment.
- Browser cannot load generated media URLs (adjust `BACKEND_PUBLIC_ENDPOINT`).

## Configuration

`frontend/config.py` currently exposes:

- `backend_endpoint`
- `backend_public_endpoint`
- `use_mock_data`
- `use_search`

Environment variables can override endpoint values:

```bash
export BACKEND_ENDPOINT="http://127.0.0.1:8000/"
export BACKEND_PUBLIC_ENDPOINT="http://127.0.0.1:8000/"
```

## Mock Mode

Mock mode returns fixture data from `frontend/assets/data_example/` instead of calling backend APIs.

1. Open `frontend/config.py`
2. Set:

```python
use_mock_data = True
```

3. Run frontend:

```bash
./scripts/start_frontend.sh
```

## Debug and Transparency Features

- **API Debug Sidebar** (`components/debug_sidebar.py`): shows last request URL/status/payload/response when debug mode is enabled.
- **Agent Reasoning Panel** (sidebar toggle in `main.py`): displays backend-returned `reasoning` or `trace` payloads when available.

## How It Works

- UI state is stored in Streamlit `st.session_state`.
- Durable state is backend-owned and retrieved via explicit endpoints (goals, profiles, runtime state, content cache, session activity, analytics).
- Frontend no longer relies on legacy monolithic user-state persistence.

## API Interface Notes

Many generation/update endpoints support optional model override fields:

- `model_provider`
- `model_name`

Frontend helpers pass these where applicable and otherwise use backend defaults from `/config` and `/list-llm-models`.

For chatbot requests specifically, the backend supports additive optional controls used by the frontend helper layer:

- `use_vector_retrieval`, `use_web_search`, `use_media_search`
- `allow_preference_updates`
- contextual fields: `user_id`, `goal_id`, `session_index`, `learner_information`
- `return_metadata` (structured response mode with profile-update metadata)

## Project Structure

```text
frontend/
  main.py                    # Streamlit entrypoint, auth gate, navigation
  config.py                  # Endpoint and mode flags
  requirements.txt           # Dependencies
  .streamlit/config.toml     # Streamlit defaults (theme/server)

  pages/
    login.py                 # Authentication (sign-in / register)
    onboarding.py            # Persona + goal input; FSLSM profile inferred
    skill_gap.py             # Gap identification and schedule handoff
    goal_management.py       # Goal CRUD and activation
    learning_path.py         # Path display + adaptation controls
    knowledge_document.py    # Learning content, audio, media, quizzes, session completion
    learner_profile.py       # Profile views; separate edit flows for FSLSM vs. learner info
    dashboard.py             # Analytics widgets

  components/                # Reusable UI pieces (chatbot, gap display, topbar, debug)
  utils/                     # API client, state management, parsing/format helpers
  assets/                    # CSS, JS, avatar, mock data
  docker/
    Dockerfile
    docker-compose.yml
```

## Backend Requirements for Full (Non-Mock) Flow

Ensure backend is running and reachable at `BACKEND_ENDPOINT`, with these endpoint groups available:

- Auth: `/auth/*`
- Goals/Profile: `/goals/*`, `/profile/*`, `/sync-profile/*`, `/propagate-profile/*`
- Learning runtime/content: `/goal-runtime-state/*`, `/learning-content/*`, `/session-activity`, `/complete-session`
- Generation/planning: `/identify-skill-gap-with-info`, `/schedule-learning-path-agentic`, `/generate-learning-content`, `/chat-with-tutor`
- Analytics: `/dashboard-metrics/*`, `/behavioral-metrics/*`
- Events: `/events/log`, `/events/{user_id}`

Backend docs: `http://localhost:8000/docs`

## Common Tasks

### Start backend and frontend together (two terminals)

Terminal 1 (repo root):

```bash
./scripts/start_backend.sh 8000
```

Terminal 2 (repo root):

```bash
./scripts/start_frontend.sh
```

### Point frontend to remote backend

Set in environment:

```bash
export BACKEND_ENDPOINT="http://<host>:<port>/"
export BACKEND_PUBLIC_ENDPOINT="http://<host>:<port>/"
./scripts/start_frontend.sh
```

### Reset to mock exploration

```python
# frontend/config.py
use_mock_data = True
```

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| App opens but actions fail | Backend unavailable or wrong endpoint | Start backend on `8000` or update `BACKEND_ENDPOINT` |
| Media/audio links fail in browser | Wrong public backend URL | Set `BACKEND_PUBLIC_ENDPOINT` to browser-reachable host |
| `docker: command not found` | Docker not installed/available in PATH | Install Docker Desktop and restart terminal |
| `Cannot connect to Docker daemon` | Docker Desktop not running | Start Docker Desktop fully |
| Port `8501` in use | Another process on same port | Run `./scripts/start_frontend.sh 8600` or update compose mapping |
| Login succeeds but no goals appear | Backend data missing/cleared for user | Check backend `/goals/{user_id}` and onboarding completion |
| Model list looks wrong/empty | Backend model config issue | Check backend `/list-llm-models` and backend config/env |

## Development Tips

- Streamlit reruns on every interaction; keep heavy work in backend APIs.
- Put reusable UI in `components/`; page-specific orchestration in `pages/`.
- Keep API shape handling centralized in `utils/request_api.py`.
- Validate UI against both modes: live backend and `use_mock_data=True`.

## License

This project is released under the repository's top-level license.
