# Frontend React of Ami

A Vite + React + TypeScript single-page application for Ami that talks to the FastAPI backend over HTTP.

This app is the newer frontend surface under active development. It is intended to replace the current Streamlit UI with a more production-oriented learner experience.

## Quickstart

### Prerequisites

- Node.js 20+
- `npm`
- A running backend instance

### Step 1 — Open a Terminal and Enter the Frontend React Folder

```bash
cd path/to/Ami/frontend-react
```

Replace `path/to/Ami` with your local path.

### Step 2 — Start the Backend

This frontend expects the FastAPI backend to already be running.

Follow the setup instructions in [`frontend/README.md`](../frontend/README.md) or [`backend/README.md`](../backend/README.md), depending on how you are running the rest of the stack.

By default, the React client uses:

```text
http://127.0.0.1:8001/
```

If your backend is running on a different port or host, set `VITE_API_BASE_URL` in the next step.

### Step 3 — Prepare `.env`

```bash
cp .env.example .env
```

Default example:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8001/
```

`VITE_API_BASE_URL` should be the backend origin. The client automatically appends `/v1` for API calls.

Examples:

- Backend on local port `8001`: `VITE_API_BASE_URL=http://127.0.0.1:8001/`
- Backend on local port `8000`: `VITE_API_BASE_URL=http://127.0.0.1:8000/`

### Step 4 — Install Dependencies

```bash
npm install
```

### Step 5 — Start the Development Server

```bash
npm run dev
```

Open the app in the browser at:

```text
http://localhost:5173
```

If `5173` is already in use, Vite will move to the next available port such as `5174`.

### Build and Preview

Create a production build:

```bash
npm run build
```

Preview the built app locally:

```bash
npm run preview
```

## Backend Connection Behavior

Frontend React resolves API calls through `src/api/client.ts`.

- `VITE_API_BASE_URL`
  - backend origin used for HTTP calls
  - default fallback in code: `http://localhost:8001/`
- API routes are served under `/v1`
  - if `VITE_API_BASE_URL` does not already end in `/v1`, the client appends it automatically

Examples:

- `VITE_API_BASE_URL=http://127.0.0.1:8001/` -> requests go to `http://127.0.0.1:8001/v1/`
- `VITE_API_BASE_URL=http://127.0.0.1:8000/` -> requests go to `http://127.0.0.1:8000/v1/`

## Structure

- **API_CONTRACT.md** — API contract (method/path, request/response schema, auth and error handling).
- **api-types.ts** — Type draft aligned with the contract; source uses the copy under `src/types/`.
- **src/**
  - **api/client.ts** — Axios instance; baseURL from `VITE_API_BASE_URL`.
  - **api/errors.ts** — Response interceptor: `401` clears token and redirects to `/login`; other errors use a toast placeholder.
  - **api/toast.ts** — Toast placeholder (replace with `react-hot-toast` / `sonner`).
  - **api/endpoints/** — By resource: auth, config, userState, profile, events, metrics, mastery, learningPath, pdf; each file exports typed TanStack Query hooks.
  - **types/** — API type definitions and re-exports.
  - **router.tsx** — React Router routes.
  - **pages/** — App pages such as Home, Login, Register, Onboarding, Goals, Profile, Learning Path, Knowledge, and Skill Gap.

## Environment

Create `.env` in the project root (see `.env.example`):

```bash
VITE_API_BASE_URL=http://127.0.0.1:8001/
```
