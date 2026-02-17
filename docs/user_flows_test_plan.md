# GenMentor — User Flows, Backend Tests & Frontend Verification Plan

> **Purpose:** This document lists each user flow's **user story**, the **backend test script** that covers it, and the **Streamlit frontend test steps** to manually verify the flow end-to-end.
>
> **How to use:** Copy this into a Google Doc so your team can check off steps and leave comments on possible bugs.

---

## Table of Contents

1. [Flow 1 — User Login / Logout](#flow-1--user-login--logout)
2. [Flow 2A — Picking a Persona](#flow-2a--picking-a-persona)
3. [Flow 2B — Uploading a Resume](#flow-2b--uploading-a-resume)
4. [Flow 2C — Setting a Learning Goal](#flow-2c--setting-a-learning-goal)
5. [Flow 2D — Refining a Learning Goal](#flow-2d--refining-a-learning-goal)
6. [Flow 2E — Determining Skill Gap & Identifying Current Level](#flow-2e--determining-skill-gap--identifying-current-level)
7. [Flow 2F — Retrieval-Grounded Skill Gap Identification](#flow-2f--retrieval-grounded-skill-gap-identification)
8. [Flow 2G — Automatic Goal Refinement](#flow-2g--automatic-goal-refinement)
9. [Flow 2H — All Skills Mastered Handling](#flow-2h--all-skills-mastered-handling)
10. [Flow 3 — User Account Deletion](#flow-3--user-account-deletion)
11. [Flow 4 — Behavioral Patterns Display (Real Metrics)](#flow-4--behavioral-patterns-display-real-metrics)
12. [Flow 5 — Knowledge Content with Verified Course Materials](#flow-5--knowledge-content-with-verified-course-materials)

---

## Flow 1 — User Login / Logout

### User Story

> **As a** learner,
> **I want to** register a new account, log in with my credentials, and log out,
> **so that** my learning progress is saved to my personal account and I can securely access it across sessions.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_store_and_auth.py` | `TestAuthStore` (10 tests) | User creation, password hashing (bcrypt), password verification, duplicate detection, user deletion, disk persistence |
| `backend/tests/test_store_and_auth.py` | `TestAuthJWT` (5 tests) | JWT token creation, verification, different users get different tokens, invalid/tampered/expired tokens return `None` |
| `backend/tests/test_auth_api.py` | `TestRegisterEndpoint` (6 tests) | `POST /auth/register` — success, returns valid JWT, rejects short username (<3 chars), rejects short password (<6 chars), rejects duplicate username (409), creates user in store |
| `backend/tests/test_auth_api.py` | `TestLoginEndpoint` (5 tests) | `POST /auth/login` — success, returns valid JWT, wrong password (401), nonexistent user (401), login after register |
| `backend/tests/test_auth_api.py` | `TestAuthMeEndpoint` (4 tests) | `GET /auth/me` — valid token returns username, invalid token (401), no token (401), works with login token |
| `backend/tests/test_auth_api.py` | `TestFullAuthLifecycle` (1 test) | End-to-end: register → login → verify token → create data → delete → verify gone |

**Run command:**
```bash
python -m pytest backend/tests/test_store_and_auth.py backend/tests/test_auth_api.py -v
```

### Streamlit Frontend Test Steps

#### 1.1 — Register a new account

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start the app (`streamlit run frontend/main.py`). Ensure backend is running. | App loads, shows the Onboarding page with a top bar |
| 2 | Click the **account icon** (top-right) | "Login / Register" dialog opens |
| 3 | Click the **Register** tab | Registration form is shown with username, password, confirm password fields |
| 4 | Enter a username shorter than 3 characters, fill password fields, click **Register** | Error: "Username must be at least 3 characters." |
| 5 | Enter a valid username, enter a password shorter than 6 characters, click **Register** | Error: "Password must be at least 6 characters." |
| 6 | Enter valid username, enter mismatched passwords, click **Register** | Error: "Passwords do not match." |
| 7 | Enter valid username (e.g., `testuser1`), matching passwords (e.g., `pass123456`), click **Register** | Dialog closes, app reruns, user is now logged in (account icon shows popover with "Signed in as **testuser1**") |
| 8 | Try registering again with the same username | Error: "Username already exists. Please choose another." |

#### 1.2 — Log in with existing account

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | If logged in, click account icon → **Log-out** | App returns to logged-out state |
| 2 | Click account icon → **Login** tab | Login form shown with username and password fields |
| 3 | Enter wrong password, click **Login** | Error: "Invalid username or password." |
| 4 | Enter correct credentials (the user you just registered), click **Login** | Dialog closes, app reruns, user is logged in. If user has previous progress, it is restored |
| 5 | Click account icon | Popover shows "Signed in as **testuser1**" |

#### 1.3 — Log out

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | While logged in, click the account icon (top-right) | Popover with username and "Log-out" button appears |
| 2 | Click **Log-out** | App reruns. Login/Register button is visible again. Onboarding page shown (no user-specific data visible) |
| 3 | Click account icon | Should show login dialog again (not the logged-in popover) |

---

## Flow 2A — Picking a Persona

### User Story

> **As a** new learner going through onboarding,
> **I want to** select a learning persona that matches my learning style,
> **so that** the platform adapts its content and teaching style to how I learn best.

### Backend Test Scripts

Persona selection happens entirely on the frontend — the selected persona's FSLSM dimensions are embedded into the `learner_information` string and persisted via the user-state endpoints.

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_user_state.py` | `TestUserStateStore` (11 tests) | `put_user_state` / `get_user_state` — the mechanism that persists persona selection (stored as part of `learner_persona` and `learner_information` keys) |
| `backend/tests/test_user_state.py` | `TestUserStateAPI` (8 tests) | `PUT /user-state/{user_id}` and `GET /user-state/{user_id}` API endpoints — verifies the persona and all session state roundtrips correctly |

**Run command:**
```bash
python -m pytest backend/tests/test_user_state.py -v
```

### Streamlit Frontend Test Steps

> **Note:** As of the single-page onboarding redesign, persona selection, resume upload, goal setting, and AI refinement all appear on one page. There are no Next/Previous card navigation buttons.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Log in (or register). Ensure onboarding is not yet completed. | Onboarding page loads showing the full single-page layout: welcome header, goal input, persona cards, resume upload, LinkedIn placeholder, and "Begin Learning" button |
| 2 | Observe the **persona selection cards** | Five cards are displayed in a row: "Hands-on Explorer", "Reflective Reader", "Visual Learner", "Conceptual Thinker", "Balanced Learner" — each with a description and a "Select" button |
| 3 | Click **"Select"** under **"Hands-on Explorer"** | Card highlights (blue border). Button changes to "✓ Selected". Session state `learner_persona` is set to "Hands-on Explorer" |
| 4 | Click **"Select"** under **"Reflective Reader"** | "Reflective Reader" card highlights, "Hands-on Explorer" is deselected. The `learner_information` string should now contain "Learning Persona: Reflective Reader (initial FSLSM: processing=0.7, perception=0.5, input=0.7, understanding=0.5)" |
| 5 | Log out, then log back in | Persona selection should be restored from backend persistence |
| 6 | Click **"Begin Learning"** without selecting a persona | Warning: "Please provide both a learning goal and select a learning persona before continuing." |

---

## Flow 2B — Uploading a Resume

### User Story

> **As a** learner during onboarding,
> **I want to** upload my resume or relevant PDF document,
> **so that** the platform can understand my background, skills, and experience to better personalize my learning path.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_onboarding_api.py` | `TestExtractPdfText` (3 tests) | `POST /extract-pdf-text` — valid PDF returns extracted text, multi-page PDF concatenates all pages, missing file returns 422 |
| `backend/tests/test_user_state.py` | `TestUserStateStore` | Verifies that the extracted PDF text (stored in `learner_information_pdf` key) persists correctly via user-state |

**Run command:**
```bash
python -m pytest backend/tests/test_onboarding_api.py::TestExtractPdfText backend/tests/test_user_state.py -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | On the Onboarding page, observe the bottom section | Two action cards are visible: "Upload Your Resume (Optional)" on the left, "Connect to your LinkedIn" on the right |
| 2 | Click the upload area and select a valid PDF file (e.g., a resume) | Spinner appears: "Extracting text from PDF...". After a moment, toast message: "PDF uploaded successfully." |
| 3 | Observe the `learner_information` value (visible in debug sidebar or by checking state) | The extracted PDF text is appended to the `learner_information` string after the persona prefix |
| 4 | Try uploading a non-PDF file (e.g., a .docx or .txt) | File uploader rejects it — only `.pdf` files accepted |
| 5 | Upload a multi-page PDF | All pages' text should be extracted and included |
| 6 | Click **"Begin Learning"** (with goal and persona filled) | App navigates to the Skill Gap page. The `learner_information` passed to `POST /identify-skill-gap-with-info` should include the resume text |
| 7 | Do NOT upload a PDF (leave it empty), click **"Begin Learning"** | Flow should work normally — PDF is optional. `learner_information_pdf` should be empty string |
| 8 | Click **"Connect LinkedIn"** button | Toast message: "LinkedIn integration coming soon!" (placeholder functionality) |

---

## Flow 2C — Setting a Learning Goal

### User Story

> **As a** learner during onboarding,
> **I want to** enter my learning goal (e.g., "Become an HR Manager" or "Learn Python for data science"),
> **so that** the platform can create a personalized learning path tailored to my specific objective.

### Backend Test Scripts

Goal setting is a frontend-only action that stores the goal text in session state. The goal is sent to the backend when the skill gap identification or profile creation endpoint is called.

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_user_state.py` | `TestUserStateStore`, `TestUserStateAPI` | Verifies the `goals` list and `to_add_goal` state persist correctly via the user-state mechanism |
| `backend/tests/test_onboarding_api.py` | `TestIdentifySkillGapEndpoint` | Verifies the `learning_goal` string is correctly passed to and processed by `POST /identify-skill-gap-with-info` |
| `backend/tests/test_onboarding_api.py` | `TestCreateLearnerProfileEndpoint` | Verifies the `learning_goal` is included in the profile created by `POST /create-learner-profile-with-info` |

**Run command:**
```bash
python -m pytest backend/tests/test_user_state.py backend/tests/test_onboarding_api.py -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | On the Onboarding page, observe the "What would you like to learn today?" section | A text input is visible with placeholder "eg : learn english, python, data ....." |
| 2 | Leave the goal input empty and click **"Begin Learning"** | Warning: "Please provide both a learning goal and select a learning persona before continuing." |
| 3 | Enter a learning goal (e.g., "I want to become an HR Manager with expertise in HRIS systems") | Input field updates, goal is stored in `to_add_goal["learning_goal"]` |
| 4 | Select a persona and click **"Begin Learning"** | App navigates to the Skill Gap page. The goal text is used for skill gap identification |
| 5 | Log out and log back in (after entering a goal but before clicking Begin Learning) | Goal text should be restored from persisted state |

---

## Flow 2D — Refining a Learning Goal

### User Story

> **As a** learner setting up my learning goal,
> **I want** the AI to automatically refine my vague goal during skill gap identification,
> **so that** my goal is clearer, more actionable, and better suited for generating an effective learning path — without me having to click a separate button.

> **Note:** As of the agentic skill gap update, AI refinement is now **automatic** during skill gap identification. The manual "AI Refinement" button has been removed from onboarding. The backend `/refine-learning-goal` endpoint still exists for potential use in goal management as a fallback.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_onboarding_api.py` | `TestRefineGoalEndpoint` (4 tests) | `POST /refine-learning-goal` — success (mocked LLM), verifies `learner_information` is forwarded, works with empty learner info, LLM failure returns 500 |
| `backend/tests/test_skill_gap_orchestrator.py` | `TestAutoRefinementLoop` (5 tests) | Auto-refinement loop: vague goal triggers refinement, non-vague does not, all-mastered does not, max 1 refinement, auto-refinement info in response |

**Run command:**
```bash
python -m pytest backend/tests/test_onboarding_api.py::TestRefineGoalEndpoint backend/tests/test_skill_gap_orchestrator.py -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | On the Onboarding page, observe the area below the learning goal input | Hint text explains that the system will automatically refine goals if needed. No manual "AI Refinement" button is present |
| 2 | Enter a vague goal (e.g., "learn about HR stuff") and click **"Begin Learning"** | App navigates to Skill Gap page. The system auto-refines the goal during identification |
| 3 | Observe the Skill Gap page after identification | If the goal was auto-refined, an info banner appears: "Your goal was automatically refined for better results." showing the original and refined goals |
| 4 | Enter a specific goal (e.g., "Learn Python for data analysis with Pandas and Matplotlib") | No auto-refinement occurs. No banner is shown |
| 5 | The goal management page still has a manual refinement button as fallback | The "AI Refinement" button in goal management still works for manual refinement |

---

## Flow 2E — Determining Skill Gap & Identifying Current Level

### User Story

> **As a** learner who has set a learning goal,
> **I want to** have the platform identify the skills required for my goal, determine my current skill levels (using my resume if available), and highlight the gaps,
> **so that** I can see exactly where I need to improve and get a learning path focused on my actual weaknesses.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_onboarding_api.py` | `TestIdentifySkillGapEndpoint` (4 tests) | `POST /identify-skill-gap-with-info` — success (mocked LLM), verifies each gap has required fields (name, is_gap, required_level, current_level), works with pre-existing skill requirements, LLM failure returns 500 |
| `backend/tests/test_onboarding_api.py` | `TestCreateLearnerProfileEndpoint` (3 tests) | `POST /create-learner-profile-with-info` — creates profile with cognitive_status/learning_preferences/behavioral_patterns, stores in profile store when user_id provided, does not store without user_id |
| `backend/tests/test_onboarding_api.py` | `TestProfileRetrieval` (4 tests) | `GET /profile/{user_id}` — get by goal_id, get all profiles for user, 404 for nonexistent user/goal |
| `backend/tests/test_onboarding_api.py` | `TestEventLogging` (3 tests) | `POST /events/log` — logs onboarding events, multiple events, auto-timestamps |
| `backend/tests/test_store_and_auth.py` | `TestProfilePersistence` (7 tests) | Profile upsert, get, overwrite, multiple goals per user, disk persistence, reload |

**Run command:**
```bash
python -m pytest backend/tests/test_onboarding_api.py backend/tests/test_store_and_auth.py::TestProfilePersistence -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete onboarding (select persona, enter goal) and click **"Begin Learning"** | App navigates to the **Skill Gap** page. Spinner appears: "Identifying Skill Gap ..." |
| 2 | Wait for skill gap identification to complete | Page updates to show a list of skills with: skill name, required level, current level, gap status (red/green), reason, confidence |
| 3 | Verify summary text | Info banner: "There are X skills in total, with Y skill gaps identified." |
| 4 | Check each skill card | Each card shows: skill name (numbered), **Required Level** pill selector (beginner/intermediate/advanced/expert), **Current Level** pill selector (unlearned/beginner/intermediate/advanced/expert), colored header (red = gap, green = no gap) |
| 5 | Expand **"More Analysis Details"** on a skill | Shows reason and confidence level. Shows warning if current < required, success message if current >= required |
| 6 | Change a skill's **Current Level** from "beginner" to "advanced" (higher than required) | Card header turns green. Gap toggle auto-disables. "Mark as Gap" toggle reflects the change. State saves automatically |
| 7 | Change a skill's **Required Level** to a higher value than current | Card header turns red. Skill is marked as a gap |
| 8 | Change a skill's **Required Level** to "expert" and **Current Level** to "advanced" | Card header turns red (gap). Skill is marked as a gap because advanced < expert |
| 9 | Change the **Current Level** to "expert" | Card header turns green. Skill is no longer a gap (expert >= expert) |
| 10 | Toggle **"Mark as Gap"** off on a gap skill | Gap is removed, current level is set to match required level |
| 11 | Verify resume influence (if resume was uploaded) | If a resume was uploaded in onboarding, the AI should have used it to set more accurate current levels. For example, if your resume says "5 years Python experience", Python-related skills should show higher current levels |
| 12 | Click **"Schedule Learning Path"** | Spinner: "Creating your profile ...". After completion, toast: "Your profile has been created!". App navigates to the **Learning Path** page. Onboarding is marked as complete (`if_complete_onboarding = True`) |
| 13 | Navigate to **My Profile** page | The created learner profile should show: cognitive status (overall progress, mastered skills, in-progress skills), learning preferences (FSLSM dimensions matching your persona), behavioral patterns |
| 14 | Navigate to **Dashboard** page | Radar chart shows 5-level radial axis: Unlearned (0), Beginner (1), Intermediate (2), Advanced (3), Expert (4). Required and current level traces are plotted correctly |

---

## Flow 2F — Retrieval-Grounded Skill Gap Identification

### User Story

> **As a** learner whose goal matches verified course content,
> **I want** the skill gap identification to be grounded in actual course material (syllabus and lectures),
> **so that** the identified skills are relevant to my actual course rather than generic LLM knowledge.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_skill_gap_tools.py` | `TestCourseContentRetrievalTool` (6 tests) | Retrieval tool: returns formatted docs, filters by category, filters by lecture_number, no results message, no VCM fallback, combined filtering |
| `backend/tests/test_skill_gap_schemas.py` | `TestGoalAssessmentSchema` (4 tests) | GoalAssessment defaults, all fields, SkillGaps with/without goal_assessment |
| `backend/tests/test_onboarding_api.py` | `TestIdentifySkillGapEndpoint` (6 tests) | Skill gap endpoint including goal_assessment in response, search_rag_manager passed |

**Run command:**
```bash
python -m pytest backend/tests/test_skill_gap_tools.py::TestCourseContentRetrievalTool backend/tests/test_skill_gap_schemas.py backend/tests/test_onboarding_api.py::TestIdentifySkillGapEndpoint -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set a learning goal matching a verified course (e.g., "Introduction to Computer Science and Programming in Python") | Goal is accepted |
| 2 | Click **"Begin Learning"** and wait for skill gap identification | Skills identified are grounded in the course syllabus (e.g., "Variables and Types", "Control Flow", "Functions") |
| 3 | Set a goal referencing specific content (e.g., "topics from lecture 3") | Skills are grounded in that specific lecture's content |
| 4 | Set a goal NOT matching any verified course (e.g., "Learn Kubernetes cluster management") | Skills are still identified using LLM knowledge (fallback). No error occurs |

---

## Flow 2G — Automatic Goal Refinement

### User Story

> **As a** learner who enters a vague learning goal,
> **I want** the system to automatically detect the vagueness and refine my goal,
> **so that** I get better skill gap results without needing to manually edit my goal.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_skill_gap_orchestrator.py` | `TestAutoRefinementLoop` (5 tests) | Vague goal triggers auto-refinement, non-vague does not, all-mastered does not, max 1 refinement, auto-refinement info in response |
| `backend/tests/test_skill_gap_tools.py` | `TestGoalAssessmentTool` (7 tests) | Vagueness detection via retrieval, all-mastered detection, suggestions |
| `backend/tests/test_skill_gap_tools.py` | `TestGoalRefinementTool` (4 tests) | Refinement output, was_refined flag, unchanged detection, empty learner info |

**Run command:**
```bash
python -m pytest backend/tests/test_skill_gap_orchestrator.py backend/tests/test_skill_gap_tools.py -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enter a vague goal (e.g., "learn stuff") and click **"Begin Learning"** | System auto-refines the goal. Skill Gap page shows info banner: "Your goal was automatically refined for better results." with original and refined goals |
| 2 | Verify the refined goal produces better skill gaps | Skill gaps are more specific and relevant than what the vague goal would have produced |
| 3 | Enter a goal that is still vague after refinement | Warning banner: "Your goal may be too vague to produce optimal results." with suggestion to make the goal more specific |
| 4 | Enter a specific goal (e.g., "Learn Python for data analysis with Pandas and Matplotlib") | No refinement needed, no banner shown. Skills are identified directly |

---

## Flow 2H — All Skills Mastered Handling

### User Story

> **As a** learner who already masters all required skills for my goal,
> **I want** the system to tell me and block scheduling a redundant learning path,
> **so that** I can change my goal to something more challenging or adjust my self-assessed skill levels.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_skill_gap_tools.py` | `TestGoalAssessmentTool` (7 tests) | All-mastered detection from skill_gaps, suggestion text |
| `backend/tests/test_skill_gap_orchestrator.py` | `TestAutoRefinementLoop::test_all_mastered_goal_no_refinement` | All-mastered goals are not auto-refined |

**Run command:**
```bash
python -m pytest backend/tests/test_skill_gap_tools.py::TestGoalAssessmentTool backend/tests/test_skill_gap_orchestrator.py::TestAutoRefinementLoop::test_all_mastered_goal_no_refinement -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set up a scenario where the learner is an expert in all required skills (e.g., expert persona with a beginner-level goal) | Skill gap identification completes |
| 2 | Observe the Skill Gap page | Info banner: "You already master all required skills for this goal." with suggestion. **"Schedule Learning Path"** button is **disabled** |
| 3 | Click **"Edit Goal"** button | Navigates back to onboarding to change the goal |
| 4 | Manually lower a skill's **Current Level** via the pill selector (create a gap) | **"Schedule Learning Path"** button becomes **enabled** |
| 5 | Raise the current level back (remove the gap) | **"Schedule Learning Path"** button becomes **disabled** again |
| 6 | In goal management dialog, same behavior applies | Schedule button disabled when no gaps, enabled when gaps exist |

---

## Flow 3 — User Account Deletion

### User Story

> **As a** user who no longer wants to use the platform,
> **I want to** permanently delete my account and all associated data,
> **so that** my personal information, learning history, and profile are completely removed from the system.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_auth_api.py` | `TestDeleteAccountEndpoint` (7 tests) | `DELETE /auth/user` — success (200), removes user from auth store, removes all user data (profiles, events, state), preserves other users' data, rejects invalid token (401), rejects no token (401), login fails after deletion |
| `backend/tests/test_store_and_auth.py` | `TestDeleteAllUserData` (3 tests) | `delete_all_user_data()` — removes profiles (all goals), removes events, removes user state, preserves other users |
| `backend/tests/test_store_and_auth.py` | `TestAuthStore` → `test_delete_user*` (3 tests) | `delete_user()` — removes user, returns False for nonexistent, persists deletion to disk |
| `backend/tests/test_auth_api.py` | `TestFullAuthLifecycle` (1 test) | Full lifecycle: register → login → create data → delete → verify everything is gone → verify login fails |

**Run command:**
```bash
python -m pytest backend/tests/test_auth_api.py::TestDeleteAccountEndpoint backend/tests/test_auth_api.py::TestFullAuthLifecycle backend/tests/test_store_and_auth.py::TestDeleteAllUserData -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Log in with an account that has completed onboarding (has goals, profiles, learning data) | App loads with the Goal Management page and full learning data |
| 2 | Navigate to **My Profile** page | Profile page shows: learner information, learning goal, cognitive status, learning preferences, behavioral patterns. "Restart Onboarding" and "Delete Account" buttons are at the bottom |
| 3 | Click **"Delete Account"** (red button at bottom) | Confirmation dialog appears: "This action is permanent. Your account and all associated data will be deleted and cannot be recovered." with **Delete** and **Cancel** buttons |
| 4 | Click **Cancel** | Dialog closes. Account and data are unchanged. Profile still visible |
| 5 | Click **"Delete Account"** again, then click **Delete** | Backend call: `DELETE /auth/user`. Success message: "Account deleted successfully." App redirects to the main page (logged-out state) |
| 6 | Try logging in with the deleted account's credentials | Error: "Invalid username or password." — account no longer exists |
| 7 | Register a new account with the same username | Should succeed — the old account was fully removed |
| 8 | Verify no old data exists for the new account | New account starts fresh: no goals, no profiles, no learning history. Onboarding starts from scratch |

---

## Flow 4 — Behavioral Patterns Display (Real Metrics)

### User Story

> **As a** learner viewing my profile,
> **I want to** see real metrics about my learning behavior (session count, average duration, total time, motivational triggers, mastery progress),
> **so that** I can understand my actual learning patterns rather than seeing generic AI-generated descriptions.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_behavioral_metrics.py` | `TestBehavioralMetrics` (7 tests) | `GET /behavioral-metrics/{user_id}` endpoint: 404 on missing user, zero metrics on empty state, session duration computation, goal filtering, trigger counting, mastery history, sessions learned count |
| `backend/tests/test_onboarding_api.py` | `TestCreateLearnerProfileEndpoint` (3 tests) | Verifies profile creation still produces valid `behavioral_patterns` (schema unchanged) |

### Streamlit Frontend Test Steps

#### 4.1 — No sessions completed (fresh profile)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete onboarding and navigate to **My Profile** | Profile page loads with all sections |
| 2 | Observe the **Behavioral Patterns** section | Section header "Behavioral Patterns" is visible |
| 3 | Check **Session Completion** | Progress bar at 0%. Caption: "0 of N sessions completed" (where N = number of sessions in the learning path) |
| 4 | Check **Session Duration & Engagement** | Info message: "No completed sessions yet. Complete a learning session to see engagement metrics." |
| 5 | Check **Motivational Triggers** | Info message: "No data yet." |
| 6 | Check **Mastery Progress** | Info message: "No mastery data yet. Study sessions to see your mastery trend." |

#### 4.2 — After completing one or more sessions

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to the learning path, start a session, and click **Complete Session** | Session marked as learned. Redirected to Learning Path page |
| 2 | Navigate to **My Profile** | Profile page loads |
| 3 | Check **Session Completion** | Progress bar reflects completion ratio. Caption: "1 of N sessions completed" |
| 4 | Check **Session Duration & Engagement** | Three metric cards visible: "Sessions Completed" (1), "Avg Duration" (X.X min), "Total Learning Time" (X.X min). Values should be realistic (not zero, not extremely large) |
| 5 | Check **Motivational Triggers** | Caption: "X motivational trigger(s) received across all sessions" (X depends on session duration; if session was < 3 min, X may be 0) |
| 6 | Complete a second session (spend at least 4 minutes to trigger motivational prompts) | Navigate back to My Profile. Sessions Completed shows 2. Avg Duration updates. Motivational triggers count increases |
| 7 | Check **Mastery Progress** | If mastery data has been recorded, shows progress bar with latest mastery rate and sample count. Otherwise shows "No mastery data yet." |

#### 4.3 — Multiple goals

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Add a second learning goal and complete onboarding for it | Second goal is created with its own learning path |
| 2 | Switch to the second goal and navigate to **My Profile** | Behavioral patterns show metrics only for the second goal (should show "No completed sessions yet" if no sessions done for this goal) |
| 3 | Switch back to the first goal | Behavioral patterns show the first goal's metrics (previously completed sessions should be reflected) |

#### 4.4 — Backend unavailable (fallback)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Stop the backend server | Backend is unreachable |
| 2 | Navigate to **My Profile** | Behavioral patterns section falls back to displaying the LLM-generated text (system usage frequency, session duration engagement, motivational triggers, additional notes) |

---

## Flow 5 — Knowledge Content with Verified Course Materials

### User Story

> **As a** learner studying a topic covered by verified course materials,
> **I want** the learning content to be sourced from curated university materials first,
> **so that** I receive accurate, high-quality educational content rather than unreliable web search results.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_verified_content.py` | `TestVerifiedContentLoader` (8 tests) | Course scanning, file loading (JSON, text, unsupported), metadata assignment, lecture number extraction, lecture number in metadata |
| `backend/tests/test_verified_content.py` | `TestVerifiedContentManager` (5 tests) | Indexing, retrieval, dedup (skip if already indexed), empty collection, course listing |
| `backend/tests/test_verified_content.py` | `TestHybridRetrieval` (4 tests) | Verified-first cascade, web fallback, no verified manager fallback, source type preservation |

**Run command:**
```bash
python -m pytest backend/tests/test_verified_content.py -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set a learning goal matching a verified course (e.g., "Introduction to Computer Science and Programming in Python") | Goal is accepted |
| 2 | Complete onboarding, schedule a learning path | Learning path is created with sessions |
| 3 | Start a session and wait for content generation | Spinners show stages 1-4. Content is generated |
| 4 | Observe the generated learning document | Content incorporates MIT 6.0001 material. Inline `[N]` citations appear in content paragraphs. A **References** section at the bottom of the document lists all sources with details (e.g., "MIT 6.0001 — Lecture 8, p.3 (Lec_8.pdf) — verified course material") |
| 5 | Verify no old source attribution banner is shown | The blue `st.info(...)` banner above the document should no longer appear |
| 6 | Set a learning goal NOT in verified content (e.g., "Learn Kubernetes cluster management") | Goal is accepted |
| 7 | Generate content for a session | Content generated using web search (fallback) |
| 8 | Observe the generated learning document | Inline `[N]` citations appear in content. The **References** section lists web search sources (e.g., "Title (https://example.com) — web search") |
| 9 | Check backend logs for source attribution | `source_type=verified_content` for step 4, `source_type=web_search` for step 7 |

---

## Test Coverage Summary

### Backend Test Files

| File | Tests | Flows Covered |
|---|---|---|
| `backend/tests/test_store_and_auth.py` | 33 | Flow 1 (auth store/JWT), Flow 2A-2E (profile/event persistence), Flow 3 (data deletion) |
| `backend/tests/test_user_state.py` | 19 | Flow 2A (persona persistence), Flow 2B (resume text persistence), Flow 2C (goal persistence) |
| `backend/tests/test_auth_api.py` | 23 | Flow 1 (register/login/me endpoints), Flow 3 (delete account endpoint + lifecycle) |
| `backend/tests/test_onboarding_api.py` | 36 | Flow 2B (PDF extract), Flow 2D (goal refinement), Flow 2E (skill gap + profile creation + event logging), Flow 2F (goal_assessment in response, search_rag_manager wiring), config + personas endpoints |
| `backend/tests/test_skill_gap_tools.py` | 17 | Flow 2F (course content retrieval tool), Flow 2G (goal assessment tool, goal refinement tool) |
| `backend/tests/test_skill_gap_schemas.py` | 4 | Flow 2F (GoalAssessment schema, SkillGaps with goal_assessment) |
| `backend/tests/test_skill_gap_orchestrator.py` | 5 | Flow 2G (auto-refinement loop: vague triggers refinement, non-vague/all-mastered do not, max 1 retry, response includes assessment) |
| `backend/tests/test_fslsm_update.py` | 2 | Flow 2A (FSLSM dimension updates — integration test, requires LLM API key) |
| `backend/tests/test_behavioral_metrics.py` | 7 | Flow 4 (behavioral metrics endpoint: computation, filtering, edge cases) |
| `backend/tests/test_verified_content.py` | 17 | Flow 5 (verified content loading, indexing, hybrid retrieval, fallback, lecture number extraction) |
| **Total** | **178** | |

### Running All Tests

```bash
# Unit tests only (no LLM/API key required):
python -m pytest backend/tests/test_store_and_auth.py backend/tests/test_user_state.py -v

# API endpoint tests (requires full backend dependencies — langchain, etc.):
python -m pytest backend/tests/test_auth_api.py backend/tests/test_onboarding_api.py backend/tests/test_behavioral_metrics.py -v

# New agentic skill gap tests:
python -m pytest backend/tests/test_skill_gap_tools.py backend/tests/test_skill_gap_schemas.py backend/tests/test_skill_gap_orchestrator.py -v

# All tests:
python -m pytest backend/tests/ -v

# Integration test (requires LLM API key):
python -m pytest backend/tests/test_fslsm_update.py -v
```

### Notes for the Team

1. **API endpoint tests** (`test_auth_api.py`, `test_onboarding_api.py`, `test_user_state.py` API section) require the full backend dependency stack (langchain, etc.) because they import `from main import app`. Run these in the dev environment with all backend dependencies installed.

2. **LLM-dependent endpoint tests** (`test_onboarding_api.py`) use **mocked LLM functions** — they do NOT call real LLM APIs. This means they test the endpoint contract (request/response shapes, error handling, store persistence) without needing API keys.

3. **Integration tests** (`test_fslsm_update.py`) call real LLMs and require an OpenAI API key configured in the environment.

4. **Frontend tests** are manual — Streamlit does not have a built-in automated testing framework. Follow the step-by-step tables above, checking each expected result. Document any deviations as bugs.

5. **Configuration endpoints** — The backend exposes two read-only configuration endpoints that the frontend (Streamlit or React) fetches at startup. These do not require authentication:
   - `GET /personas` — Returns the learning persona definitions (names, descriptions, FSLSM dimension values).
   - `GET /config` — Returns application configuration: skill levels (`["unlearned", "beginner", "intermediate", "advanced", "expert"]`), default session count, default LLM type/method, FSLSM threshold values and labels, motivational trigger interval, and max refinement iterations. The frontend falls back to local defaults if the backend is unreachable.
