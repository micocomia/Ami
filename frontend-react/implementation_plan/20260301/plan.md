# React Frontend — Feature Parity Implementation Plan
**Date:** 2026-03-01
**Branch:** `sprint-4-engine`
**Goal:** Bring `frontend-react/` to full API parity with the Streamlit frontend so the React app can immediately replace it.

---

## Overview

The React frontend (`frontend-react/`) was a well-scaffolded app with working shell layouts, API client infrastructure, and page components — but all pages used mock data. This plan describes the 15-phase implementation that replaced every mock with real API calls and added the Ami global chatbot.

---

## Phase 1 — Extend `src/types/api-types.ts`

**Status: Complete**

Added all missing types required by the new endpoint modules and pages:

| Type | Purpose |
|---|---|
| `GoalAggregate` | Full goal object (replaces thin `GoalInState`) |
| `GoalsListResponse` | `GET /goals/{user_id}` response |
| `GoalCreateRequest` / `GoalUpdateRequest` | Goal mutation payloads |
| `GoalRuntimeState` / `GoalRuntimeStateSession` | Session lock/mastery/navigation state |
| `LearningContentResponse` | Content + quizzes + view model |
| `ContentSection` / `ContentViewModel` | Paginated section structure |
| `GenerateLearningContentRequest` | Generate content payload |
| `SessionActivityRequest/Response` | Start/heartbeat/end events |
| `CompleteSessionRequest/Response` | Session completion (returns updated goal) |
| `SubmitContentFeedbackRequest/Response` | Feedback (returns updated goal) |
| `DashboardMetricsResponse` | Skill radar + time series + mastery series |
| `LearnerInformationUpdateRequest` | Update learner text/PDF profile |
| Extended `ChatWithTutorRequest` | Added `user_id`, `goal_id`, `session_index`, `learner_information` |

Also updated `src/types/index.ts` to re-export all new and existing types. Removed stale `GoalInState` re-export.

---

## Phase 2 — Authentication Foundation

**Status: Complete**

- **`src/context/AuthContext.tsx`** — Stores `userId` (= username) in `localStorage` as `ami_user_id`. Token managed by `auth.ts`. `login()`, `logout()` (clears both keys + `queryClient.clear()`), `isAuthenticated`.
- **`src/hooks/useAuth.ts`** — Thin wrapper around `AuthContext`.
- **`src/router.tsx`** — Added `AuthGuard` (redirects unauthenticated to `/login`), `RootRedirect` (routes to `/learning-path`, `/onboarding`, or `/login` based on auth + goals state). Restructured routes into auth-gated groups.
- **`src/pages/LoginPage.tsx`** — Wired to `useLogin()`; calls `authContext.login(data)` on success.
- **`src/pages/RegisterPage.tsx`** — Wired to `useRegister()`; navigates to `/onboarding` on success.
- **`src/components/shell/TopBar.tsx`** — Shows authenticated `userId`; logout button.

---

## Phase 3 — Goals Context & API Hooks

**Status: Complete**

- **`src/api/endpoints/goals.ts`** — `listGoalsApi`, `createGoalApi`, `patchGoalApi`, `deleteGoalApi`, `getGoalRuntimeStateApi`; corresponding hooks `useGoals`, `useCreateGoal`, `usePatchGoal`, `useDeleteGoal`, `useGoalRuntimeState`.
- **`src/context/GoalsContext.tsx`** — Caches all goals via React Query. `selectedGoalId` persisted in `sessionStorage`. Exposes `updateGoal(goalId, goal)` for in-place replacement (avoids refetch after `completeSession` / `submitContentFeedback`).
- **`src/hooks/useActiveGoal.ts`** — Returns `goals.find(g => g.id === selectedGoalId) ?? goals[0] ?? null`.

---

## Phase 4 — Missing Endpoint Modules

**Status: Complete**

- **`src/api/endpoints/skillGap.ts`** — `useIdentifySkillGap`, `useAuditSkillGapBias`, `useCreateLearnerProfileWithInfo`, `useValidateProfileFairness`.
- **`src/api/endpoints/content.ts`** — `useGetLearningContent` (staleTime: Infinity, retry: false, 404 resolves not rejects), `useGenerateLearningContent` (300s AbortController), `useDeleteLearningContent`, `useSessionActivity`, `useCompleteSession`, `useSubmitContentFeedback`, `useDashboardMetrics`, `useUpdateLearningPreferences`, `useUpdateLearnerInformation`, `useDeleteUserData`.
- **`src/api/endpoints/chat.ts`** — `useChatWithTutor`.
- **`src/api/endpoints/index.ts`** — Barrel-exports all endpoint modules.

---

## Phase 5 — App Startup

**Status: Complete**

- **`src/components/AppStartup.tsx`** — Mounts inside providers; calls `useAppConfig()` and `useLlmModels()` to warm the React Query cache. Returns `null`.
- **`src/main.tsx`** — Updated provider composition: `QueryClientProvider > AuthProvider > GoalsProvider > ToastProvider > AppStartup + RouterProvider`.

---

## Phase 6 — Onboarding Page

**Status: Complete**
**File:** `src/pages/OnboardingPage.tsx`

- Fetches persona cards from `usePersonas()` (key = persona name, value = `PersonaInfo`).
- Free-text learning goal input.
- PDF upload via hidden `<input type="file">` → `useExtractPdfText()` → stored as `resumeText`.
- Constructs `learnerInformation` from persona FSLSM dimensions + resume text.
- Validation: persona selected AND goal non-empty before "Begin Learning" is enabled.
- On submit: navigates to `/skill-gap` with `location.state: { goal, personaKey, learnerInformation, isGoalManagementFlow: false }`.

---

## Phase 7 — Skill Gap Page

**Status: Complete**
**File:** `src/pages/SkillGapPage.tsx`

- On mount: auto-fires `useIdentifySkillGap()` via `hasFiredRef` (prevents double-fire in StrictMode).
- After identify: auto-fires `useAuditSkillGapBias()`.
- Banners: auto-refined goal, vague goal warning, all-mastered info, bias warnings, ethical disclaimer.
- Retrieved sources collapsible.
- `SkillCard` sub-component with `LevelTrack` (visual level slider using `config.skill_levels`).
- "Schedule Learning Path" flow (disabled if zero skills selected):
  1. `createLearnerProfileWithInfoApi` → learner profile
  2. `validateProfileFairnessApi` (skipped if `isGoalManagementFlow`)
  3. `createGoalApi` (raw function, avoids hook-in-callback)
  4. `syncProfileApi` → backend sync
  5. `refreshGoals()` → `setSelectedGoalId(newGoalId)` → navigate `/learning-path`

---

## Phase 8 — Learning Path Page

**Status: Complete**
**Files:** `src/pages/LearningPathPage.tsx`, `src/components/learning/SessionCard.tsx`, `src/components/learning/index.ts`

**SessionCard:**
- Props: `index`, `pathSession: LearningPathSession`, `runtimeSession?: GoalRuntimeStateSession`, `onLaunch`, `disabled`.
- Shows lock/mastery/completed badges based on runtime state.
- Button label: "Locked" | "Review" | "Start" based on `is_locked`, `if_learned`.

**LearningPathPage:**
- Auto-schedules via `scheduleLearningPathAgenticApi({ learner_profile })` with 120s AbortController if no `learning_path` on goal.
- After scheduling: `patchGoalApi(..., { learning_path, plan_agent_metadata: result.agent_metadata })` → `refreshGoals()`.
- Auto-adapts if `runtimeState.adaptation.suggested` via `adaptLearningPathApi({ user_id, goal_id, new_learner_profile })`.
- FSLSM check: `fslsm_input <= -threshold` → Module Map (node chain); else → standard session list.
- Plan Quality panel from `activeGoal.plan_agent_metadata.evaluation`.
- Goal selector dropdown wired to `GoalsContext`.
- Launch: `useSessionActivity({ event_type: 'start' })` → navigate `/learning-session` with `{ goalId, sessionIndex }`.

---

## Phase 9 — Learning Session Page

**Status: Complete**
**Files:** `src/pages/LearningSessionPage.tsx`, `src/components/learning/QuizPanel.tsx`

**QuizPanel:**
- Renders all 5 question types: single choice, multiple choice, true/false, short answer, open-ended.
- Submits to `/mastery-evaluation` via direct `apiClient.post`.
- Post-submission: correct/wrong highlighting, SOLO level color for open-ended.
- Retake Quiz clears all state; Show Explanations toggles per-question explanations.

**LearningSessionPage:**
- `useGetLearningContent` cache check (staleTime: Infinity). 404 → triggers `useGenerateLearningContent` with 300s AbortController.
- Section pagination from `content.view_model.sections` or regex-parsed markdown fallback.
- Left TOC sidebar (click to jump section); Prev/Next buttons.
- `quizUnlocked = true` when `currentSectionIdx >= sections.length - 1`.
- Audio format: info banner + `<audio controls src={absolutize(audioUrl)}>` (prepends `VITE_API_BASE_URL` to `/static/...`).
- Heartbeat interval (configurable via `motivational_trigger_interval_secs`).
- Complete button gated by `canComplete && !(navigationMode === 'linear' && masteryResult && !masteryResult.is_mastered)`.
- Star-rating feedback (clarity/relevance/depth + engagement + comments) → `useSubmitContentFeedback` → `updateGoal()`.
- Inline right-panel chatbot with rolling 20-message window → `useChatWithTutor`.

---

## Phase 10 — Goal Management Page

**Status: Complete**
**File:** `src/pages/GoalsPage.tsx`

- Lists all active goals with progress bar (learned / total sessions).
- Inline edit → `usePatchGoal({ learning_goal })` → `refreshGoals()`.
- Confirm-delete → `useDeleteGoal()` → `refreshGoals()`.
- Add goal → navigate to `/skill-gap` with `isGoalManagementFlow: true`.
- Switch active goal → `setSelectedGoalId(goalId)` → navigate `/learning-path`.

---

## Phase 11 — Learner Profile Page

**Status: Complete**
**Files:** `src/pages/ProfilePage.tsx`, `src/components/profile/FslsmSliders.tsx`, `src/components/profile/EditProfileModal.tsx`, `src/components/profile/index.ts`

**FslsmSliders:**
- 4 dimensions: `active_reflective`, `sensing_intuitive`, `visual_verbal`, `sequential_global`.
- Label pairs from `AppConfig.fslsm_thresholds[dim]`.
- Read-only (visual bar) or editable (`<input type="range" min=-1 max=1 step=0.1>`).

**EditProfileModal (two-tab):**
- **Learning Preferences**: editable `FslsmSliders` → `useUpdateLearningPreferences` → `onUpdate(updatedGoal)`.
- **Learner Information**: textarea + PDF upload → `useUpdateLearnerInformation` → `onUpdate(updatedGoal)`.

**ProfilePage:**
- Behavioral metrics grid (6 KPIs) via `useBehavioralMetrics`.
- Read-only FSLSM sliders.
- Fairness banner with risk level + flags expander.
- Edit Profile → `<EditProfileModal>`.
- Restart onboarding: `useDeleteUserData()` → `refreshGoals()` → `/onboarding`.
- Delete account: `useDeleteUser()` → `logout()` → `/login`.

---

## Phase 12 — Analytics Page

**Status: Complete**
**Files:** `src/pages/AnalyticsPage.tsx`, `src/components/analytics/SkillRadarChart.tsx`, `src/components/analytics/SessionTimeChart.tsx`, `src/components/analytics/MasteryChart.tsx`, `src/components/analytics/index.ts`

**Charts (Recharts):**
- `SkillRadarChart` — `RadarChart` with two overlaid fills: Required (indigo) + Current (emerald).
- `SessionTimeChart` — `BarChart`, x = session index, y = duration in minutes.
- `MasteryChart` — `LineChart`, x = session index, y = mastery % with 0–100 domain.

**AnalyticsPage:**
- `useDashboardMetrics(userId, activeGoal?.id)` for all data.
- KPI cards: Overall Progress, Active Goals, Sessions Completed, Skills Tracked.
- Goal selector dropdown → `setSelectedGoalId` → metrics refetch.
- Charts only render when the respective time series has data.

---

## Phase 13 — Ami Global Chatbot

**Status: Complete**
**Files:** `src/components/chatbot/AmiChatbot.tsx`, `src/components/shell/AppShell.tsx`

**AmiChatbot:**
- Fixed-position floating button (bottom-right, z-50).
- Slide-in drawer from right (CSS `translateX` transition), 380px wide on desktop.
- Chat history in local state (not persisted). Rolling 20-message window sent to API.
- `useChatWithTutor` mutation; passes `messages`, `learner_profile`, `user_id`, `goal_id`, `learner_information`.
- On `updated_learner_profile` in response: `updateGoal(activeGoal.id, { ...activeGoal, learner_profile: updated })`.
- Enter to send, Shift+Enter for newline.

**AppShell:** Added `<AmiChatbot />` after `<Outlet />`.

---

## Phase 14 — Cleanup

**Status: Complete**

| Action | File |
|---|---|
| Deleted | `src/context/HasEnteredGoalContext.tsx` |
| Deleted | `src/pages/KnowledgePage.tsx` |

Both had zero remaining imports or references across the codebase.

`SideNav.tsx` already used `useGoalsContext` directly — no changes needed.
`main.tsx` already used `AuthProvider` + `GoalsProvider` — no changes needed.

---

## Phase 15 — README Update

**Status: Complete**
**File:** `frontend-react/README.md`

Rewrote with:
- Prerequisites, setup, run, build instructions.
- Environment variables.
- Full `src/` directory tree with descriptions.
- Key architectural patterns (auth, goals, content generation, chatbot, charts).

---

## Key Architecture Decisions

| Decision | Rationale |
|---|---|
| `AuthContext` stores only `userId`; token in `auth.ts` | Single source of truth per concern |
| `GoalsContext.updateGoal()` for in-place replace | Avoids extra `GET /goals` after `completeSession` / `submitFeedback` |
| `selectedGoalId` in `sessionStorage` | Persists across page navigations, cleared on tab close |
| 300s AbortController for content generation | Backend can take 3–5 min for long sessions |
| 120s AbortController for agentic scheduling | Agentic path can take 1–2 min |
| Content 404 → generate (no toast) | `validateStatus: s < 500` prevents axios error; page detects 404 manually |
| Rolling 20-message window for chatbot | Keeps API payload bounded without losing recent context |
| Quiz unlocks on last section only | Ensures learner reads all content before testing |

---

## Critical Gotchas Discovered

1. **`scheduleLearningPathAgenticApi`** only accepts `{ learner_profile: string, session_count?: number }` — NOT `learning_goal`, `skill_gaps`, `user_id`, `goal_id`.
2. **`adaptLearningPathApi`** takes `{ user_id, goal_id, new_learner_profile }` — NOT `current_learning_path`.
3. **`ScheduleLearningPathAgenticResponse.agent_metadata`** — field is `agent_metadata`, not `plan_agent_metadata`; mapped on store: `patchGoalApi(..., { plan_agent_metadata: result.agent_metadata })`.
4. **`deleteUserApi`** takes no arguments — uses JWT from header; calling `mutateAsync(userId)` causes TS error.
5. **Audio URLs are relative** (`/static/audio/...`) — must prepend `VITE_API_BASE_URL` before using in `<audio src>`.
6. **`GoalAggregate.[key: string]: unknown`** index signature causes `learning_path` to widen to `unknown` — cast to `LearningPathSession[]` at usage sites.
7. **Hook-in-callback problem** in SkillGapPage — solved by using raw API functions (`createGoalApi`, `syncProfileApi`) directly instead of React Query hooks.
8. **`hasFiredRef` pattern** used to prevent double-fire of auto-mutations (identify skill gap, schedule path, adapt path) under React StrictMode double-invoke.
