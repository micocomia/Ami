# frontend-react

Vite + React + TypeScript frontend for the FastAPI backend.

## Run

```bash
npm install
npm run dev
```

Open http://localhost:5173/ in the browser (or 5174 etc. if 5173 is in use).

## Structure

- **API_CONTRACT.md** — API contract (method/path, request/response schema, auth and error handling).
- **api-types.ts** — Type draft aligned with the contract; source uses the copy under `src/types/`.
- **src/**
  - **api/client.ts** — Axios instance; baseURL from `VITE_API_BASE_URL` (default `http://localhost:8000`).
  - **api/errors.ts** — Response interceptor: 401 clears token and redirects to `/login`; other errors use toast placeholder.
  - **api/toast.ts** — Toast placeholder (replace with react-hot-toast / sonner).
  - **api/endpoints/** — By resource: auth, config, userState, profile, events, metrics, mastery, learningPath, pdf; each file exports typed TanStack Query hooks.
  - **types/** — API type definitions and re-exports.
  - **router.tsx** — React Router routes.
  - **pages/** — Placeholder pages: Home, Login, Register, Onboarding, Goals, Profile, Learning Path, Knowledge, Skill Gap.

## Environment

Create `.env` in the project root (see `.env.example`):

```
VITE_API_BASE_URL=http://localhost:8000/
```
