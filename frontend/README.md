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

## Interface Walkthrough

The screenshots below show the Streamlit interface, which includes all features — including some that are still being ported to the React frontend.

### 1. Login

![Login](../assets/Beta/0%20-%20Login.png)

Returning learners sign in to access their personalized learning sessions and pick up where they left off.

### 2. Onboarding

![Onboarding](../assets/Beta/1%20-%20Onboarding.png)

During onboarding, learners choose a learning persona, describe their goal, and optionally upload a résumé so Ami can tailor the experience from the start.

### 3. Skill Gap Identification

![Skill gap analysis](../assets/Beta/2A%20-%20Skill%20Gap.png)

Ami analyzes the learner's goal and background to identify exactly which skills need to be built to reach it.

| Verified Course Content | Fairness Check |
|---|---|
| ![Skill gap with verified content](../assets/Beta/2C%20-%20Skill%20Gap%20%28Verified%20Content%29.png) | ![Skill gap bias audit](../assets/Beta/2B%20-%20Skill%20Gap%20%28Bias%29.png) |

Left: skill gap output grounded in indexed course materials.
Right: a built-in fairness review flags any assumptions in the analysis that could disadvantage certain learners.

### 4. Learning Path Personalization

| Active / Visual Learner | Reflective / Verbal Learner |
|---|---|
| ![Learning path visual persona](../assets/Beta/3A%20-%20Learning%20Path%20%28Active-Sensing-Visual-Sequential%29.png) | ![Learning path verbal persona](../assets/Beta/3B%20-%20Learning%20Path%20%28Reflective-Intuitive-Verbal-Global%29.png) |

Ami generates a personalized sequence of sessions adapted to each learner's style and knowledge level. The same goal produces a different path depending on how the learner thinks and learns.

### 5. Learning Session and Content Delivery

![Learning session visual persona](../assets/Beta/4A.I%20-%20Learning%20Session%20%28Active-Sensing-Visual-Sequential%29.png)

![Learning session verbal](../assets/Beta/4B.I%20-%20Learning%20Session%20%28Reflective-Intuitive-Verbal-Global%29.png)

Session content is adapted to the learner's preferred style — diagrams and worked examples for visual learners; narrative explanations and structured outlines for verbal learners.

![Plan quality](../assets/Beta/4C%20-%20Plan%20Quality.png)

Before delivering a learning path, Ami runs a self-evaluation loop to confirm the plan is coherent, well-sequenced, and appropriate for the learner's current level.

### 6. Adaptive Quizzes and Knowledge Checks

| Foundational-Level Quiz | Intermediate-Level Quiz |
|---|---|
| ![Beginner quiz](../assets/Beta/5A%20-%20Quiz%20%28Beginner%29.png) | ![Intermediate quiz](../assets/Beta/5B%20-%20Quiz%20%28Intermediate%29.png) |

Left: quiz questions calibrated for learners building foundational understanding.
Right: quiz questions for learners ready to apply and connect concepts across topics.

![SOLO-based open-ended assessment](../assets/Beta/5C.%20Quiz%20-%20Assessment%20using%20SOLO.png)

Open-ended responses are evaluated by an AI grader aligned with the SOLO Taxonomy — a research-backed framework that measures depth of understanding.

### 7. Ami Chatbot Tutor

![Ami chatbot](../assets/Beta/6%20-%20Chatbot.png)

Ami is available throughout the learning experience as a conversational tutor. Learners can ask follow-up questions, request clarifications, or dig deeper into any topic.

### 8. Learner Profile

| Learner Information and Cognitive Status | Learning Preferences and Patterns |
|---|---|
| ![Learner profile info and cognitive status](../assets/Beta/7%20-%20Learner%20Profile%20%28Learner%20Information%20and%20Cognitive%20Status%29.png) | ![Learner profile preferences and patterns](../assets/Beta/7B%20-%20Learner%20Profile%20%28Preferences%20and%20Patterns%29.png) |

Left: cognitive progress and learner background.
Right: learning style preferences and behavioral patterns accumulated across sessions.

### 9. Edit Profile

| Learning Style Preferences | Personal Information |
|---|---|
| ![Edit FSLSM profile](../assets/Beta/8A%20-%20Edit%20Profile%20%28FSLSM%29.png) | ![Edit learner information](../assets/Beta/8B%20-%20Edit%20Profile%20%28Learner%20Information%29.png) |

Learners can update their learning style preferences and personal background independently, so changes in one area do not affect the other.

### 10. Goal Management

![Goal management page](../assets/Beta/9%20-%20Goal%20Management.png)

Learners can create, switch between, and manage multiple learning goals — making it easy to pursue different topics or return to something set aside earlier.

### 11. Learning Analytics

![Learning analytics dashboard](../assets/Beta/10%20-%20Analytics%20Dashboard.png)

The analytics dashboard surfaces progress, skill mastery, session time, and quiz performance — helping learners understand how they are advancing and where to focus next.

---

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
