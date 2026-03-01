# Ami — React Frontend

A React + TypeScript SPA for Ami that supports authentication, onboarding, skill-gap analysis, learning-path navigation, in-session learning documents with multi-modal content, learner profile management, and an analytics dashboard.

This frontend talks to the FastAPI backend over HTTP and uses React Query to manage server state.

> **Note:** This React SPA is the planned Beta frontend (target: Mar 18, 2026), replacing the Streamlit interface with a more polished, production-grade learner experience.

---

## Current App Flow

The app is auth-gated and goal-aware:

1. **Login / Register** — JWT-based auth; token persisted in `localStorage`
2. **Onboarding** — Persona selection → FSLSM profile inferred + free-text goal + optional resume PDF upload
3. **Skill Gap** — Two-loop reflexion + bias audit; learner selects skills to include in the path
4. **Learning Path** — Agentic path scheduling; FSLSM-aware module map or standard list view
5. **Learning Session** — Paginated content sections + audio + inline quiz; heartbeat tracking; complete + feedback flow
6. **Goal Management** — Add, edit, delete, and switch between learning goals
7. **Learner Profile** — Behavioral metrics; separate edit flows for FSLSM learning style vs. personal information
8. **Analytics** — Skill radar, session time chart, mastery-over-time chart

If the user already has goals, the app routes directly into post-onboarding pages after login.

---

## How the Frontend Uses the Backend Pipelines

The React pages are thin orchestration and UI layers on top of backend pipelines:

- **Onboarding + Skill Gap** call the reflexion-enabled skill-gap flow (`/identify-skill-gap-with-info`) that performs goal clarification, skill-gap critique, and mandatory bias audit.
- **Learning Path** uses agentic planning and adaptation endpoints (`/schedule-learning-path-agentic`, `/adapt-learning-path`) backed by embedded plan feedback simulation.
- **Learning Session** consumes `/generate-learning-content`, which runs the full backend quality pipeline (draft evaluation, FSLSM-aware adaptation, targeted repair) before returning document + quiz + audio payloads. A 300-second timeout is used as generation can take several minutes.
- **Session Prefetch**: `ContentPrefetchService` runs in the backend background; subsequent sessions are prefetched while the learner works through the current one, reducing transition wait times.
- **Chatbot** calls `/chat-with-tutor`, where the backend assembles runtime tools per request (session content retrieval, vector retrieval, web-ephemeral retrieval, media search, optional signal-gated FSLSM preference update). The floating Ami button is available on all main app pages.
- **Learner Profile** uses separate scoped update endpoints: `/update-learning-preferences` for FSLSM dimensions and `/update-learner-information` for personal/background details.

---

## Quickstart

### Prerequisites

- **Node.js 18+** — [Download](https://nodejs.org/en/download)
- **Backend running at `http://localhost:8000`** — see `backend/README.md`

Verify your Node version:

```bash
node -v   # should print v18.x.x or higher
```

---

### Option A: Local Setup (Recommended for development)

#### Step 1 — Enter the frontend folder

```bash
cd path/to/Ami/frontend-react
```

Replace `path/to/Ami` with your local path.

#### Step 2 — Start the backend

The frontend requires a running backend. From the repo root in another terminal:

```bash
./scripts/start_backend.sh 8000
```

Or manually:

```bash
cd backend
conda activate ami-backend
uvicorn main:app --reload
```

#### Step 3 — Create your environment file

```bash
cp .env.example .env
```

The default `.env` points to `http://localhost:8000/`. If your backend runs on a different port, update `VITE_API_BASE_URL` accordingly.

#### Step 4 — Install dependencies

```bash
npm install
```

#### Step 5 — Start the dev server

```bash
npm run dev
```

Open in browser:

```text
http://localhost:5173
```

The dev server hot-reloads on file changes. If port 5173 is in use, Vite will automatically increment to 5174, 5175, etc. and print the actual URL.

#### Stopping

Press `Ctrl + C` in the terminal running `npm run dev`.

---

### Option B: Production Build

Build the app to static files (outputs to `dist/`):

```bash
npm run build
```

Preview the production build locally:

```bash
npm run preview
```

---

## Backend Connection Behavior

The frontend resolves the backend URL through the `VITE_API_BASE_URL` environment variable.

| Variable | Purpose | Default |
|---|---|---|
| `VITE_API_BASE_URL` | API base URL for all HTTP calls and static asset URLs (audio) | `http://localhost:8000/` |

The Axios client (`src/api/client.ts`) uses this value as `baseURL`. Audio and static assets returned by the backend as relative paths (e.g. `/static/audio/...`) are absolutized by prepending `VITE_API_BASE_URL` before use in `<audio>` elements.

### Pointing to a remote backend

Edit `.env`:

```
VITE_API_BASE_URL=http://<host>:<port>/
```

Then restart the dev server.

---

## Configuration

`.env` (copied from `.env.example`) currently exposes:

```
VITE_API_BASE_URL=http://localhost:8000/   # Backend API + static assets base URL
```

All `VITE_` prefixed variables are inlined by Vite at build time and accessible via `import.meta.env.VITE_*`.

---

## Project Structure

```
frontend-react/
  .env.example              # Environment variable template
  package.json              # Dependencies and npm scripts
  vite.config.ts            # Vite + React plugin config
  tsconfig.json             # TypeScript config
  tailwind.config.js        # Tailwind CSS config

  src/
    main.tsx                # App entry point; provider composition
    App.tsx                 # Root component
    router.tsx              # Route definitions; AuthGuard; RootRedirect
    index.css               # Tailwind base + custom CSS variables

    api/
      client.ts             # Axios instance; baseURL from VITE_API_BASE_URL
      errors.ts             # 401 interceptor → clears token, redirects /login
      endpoints/
        auth.ts             # login, register, delete user
        goals.ts            # CRUD goals, runtime state
        config.ts           # app config, LLM models, personas
        content.ts          # learning content, session activity, complete, feedback, dashboard metrics
        chat.ts             # chat-with-tutor
        metrics.ts          # behavioral metrics, quiz mix, mastery status
        profile.ts          # sync profile, learning preferences/information update
        pdf.ts              # PDF text extraction
        skillGap.ts         # identify skill gap, create learner profile, audit bias, validate fairness
        learningPath.ts     # schedule (agentic), adapt path

    components/
      analytics/            # SkillRadarChart, SessionTimeChart, MasteryChart (Recharts)
      chatbot/              # AmiChatbot — floating global tutor assistant
      learning/             # SessionCard, QuizPanel
      profile/              # FslsmSliders, EditProfileModal
      shell/                # AppShell, SideNav, TopBar, OnboardingLayout, LearningSessionLayout
      ui/                   # Button, Input, Select, Toast, etc.
      AppStartup.tsx        # Warms React Query cache on mount

    context/
      AuthContext.tsx       # userId stored in localStorage; token managed by auth.ts
      GoalsContext.tsx      # goals list cache; selectedGoalId in sessionStorage

    hooks/
      useActiveGoal.ts      # returns goals.find(selectedGoalId) ?? goals[0] ?? null
      useAuth.ts            # thin wrapper around AuthContext

    pages/
      LoginPage.tsx            # wired to useLogin()
      RegisterPage.tsx         # wired to useRegister()
      OnboardingPage.tsx       # persona selection, PDF upload, goal input
      SkillGapPage.tsx         # skill gap analysis, schedule learning path
      LearningPathPage.tsx     # session list, agentic scheduling, FSLSM module map
      LearningSessionPage.tsx  # paginated content, quiz, heartbeat, complete, feedback, inline chat
      GoalsPage.tsx            # goal CRUD, switch active goal
      ProfilePage.tsx          # behavioral metrics, FSLSM sliders, edit modal
      AnalyticsPage.tsx        # dashboard metrics, skill radar, session time, mastery charts
      HomePage.tsx             # dashboard landing

    types/
      api-types.ts          # All API TypeScript interfaces (source of truth for types)
      index.ts              # Re-exports from api-types.ts

  API_CONTRACT.md           # Full endpoint reference (method, path, request/response shapes)
  implementation_plan/      # Sprint implementation plans
```

---

## Backend Requirements for Full Flow

Ensure the backend is running and reachable at `VITE_API_BASE_URL`, with these endpoint groups available:

- **Auth**: `/auth/register`, `/auth/login`, `/auth/me`, `/auth/user`
- **Config**: `/config`, `/personas`, `/list-llm-models`
- **Goals / Profile**: `/goals/*`, `/profile/*`, `/sync-profile/*`, `/goal-runtime-state/*`
- **Learning content / sessions**: `/learning-content/*`, `/generate-learning-content`, `/session-activity`, `/complete-session`, `/submit-content-feedback`
- **Generation / planning**: `/identify-skill-gap-with-info`, `/create-learner-profile-with-info`, `/schedule-learning-path-agentic`, `/adapt-learning-path`, `/chat-with-tutor`
- **Analytics**: `/dashboard-metrics/*`, `/behavioral-metrics/*`

Backend API docs (when running): `http://localhost:8000/docs`

---

## Common Tasks

### Start backend and frontend together (two terminals)

Terminal 1 — backend (repo root):

```bash
./scripts/start_backend.sh 8000
```

Terminal 2 — frontend:

```bash
cd frontend-react
npm run dev
```

### Point frontend to a remote backend

Edit `.env`:

```
VITE_API_BASE_URL=http://<host>:<port>/
```

Restart the dev server after changing `.env`.

### Rebuild after adding a dependency

```bash
npm install
npm run dev
```

### Type-check without building

```bash
node node_modules/typescript/bin/tsc --noEmit
```

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| App opens but login/register fails | Backend unavailable or wrong URL | Start backend on port 8000 or update `VITE_API_BASE_URL` in `.env` |
| Stuck on loading after login | Goals endpoint failing | Check backend `/goals/{user_id}` and backend logs |
| Audio does not play in sessions | Wrong base URL for static files | Ensure `VITE_API_BASE_URL` matches the browser-reachable backend URL |
| "Failed to fetch personas" on onboarding | Backend `/personas` not responding | Start backend and verify `http://localhost:8000/personas` returns 200 |
| Content generation spinner runs a long time | Expected for first load | Generation takes 2–5 min; a 300-second spinner is normal; click Regenerate if it exceeds that |
| Port 5173 already in use | Another process or dev server | Vite auto-increments; check the terminal output for the actual URL |
| `node_modules` missing or stale | Dependencies not installed | Run `npm install` |
| TypeScript errors after pulling changes | New types added upstream | Run `npm install` then check `tsc --noEmit` output |
| Login succeeds but no goals appear | No goals created for this user yet | Complete onboarding (persona → skill gap → schedule path) to create the first goal |
| Model list empty or wrong | Backend model config issue | Check backend `/list-llm-models` and verify `backend/.env` has valid API keys |

---

## Development Tips

- React Query re-fetches on window focus by default; keep this in mind when debugging stale data.
- All API shapes are defined in `src/types/api-types.ts` — update types there when the backend schema changes, then update `src/types/index.ts` re-exports.
- Keep page components as orchestration layers; push reusable logic into `src/api/endpoints/` hooks or `src/components/`.
- The `API_CONTRACT.md` in this folder is the authoritative frontend-facing endpoint reference.

---

## License

This project is released under the repository's top-level license.
