# GenMentor — User Flows, Backend Tests & Frontend Verification Plan

> **Purpose:** This document lists each user flow's **user story**, the **backend test script** that covers it, and the **Streamlit frontend test steps** to manually verify the flow end-to-end.
>
> **Prerequisites for most flows:** Log in or register (see Flow 1). Complete onboarding by selecting a persona, entering a learning goal, and clicking "Begin Learning" (see Flow 2). These setup steps are not repeated in every flow.

---

## Table of Contents

1. [Flow 1 — User Login / Logout](#flow-1--user-login--logout)
2. [Flow 2 — Onboarding (Persona, Resume, Goal, Skill Gap)](#flow-2--onboarding-persona-resume-goal-skill-gap)
3. [Flow 3 — User Account Deletion](#flow-3--user-account-deletion)
4. [Flow 4 — Behavioral Patterns Display (Real Metrics)](#flow-4--behavioral-patterns-display-real-metrics)
5. [Flow 5 — Knowledge Content with Verified Course Materials](#flow-5--knowledge-content-with-verified-course-materials)
6. [Flow 6 — FSLSM-Driven Learning Path and Content Adaptations](#flow-6--fslsm-driven-learning-path-and-content-adaptations)
7. [Flow 7 — Mastery Lock and Quiz-Based Mastery Evaluation](#flow-7--mastery-lock-and-quiz-based-mastery-evaluation)
8. [Flow 8 — Agentic Learning Plan Generation](#flow-8--agentic-learning-plan-generation)
9. [Flow 9 — Adaptive Plan Regeneration](#flow-9--adaptive-plan-regeneration)
10. [Flow 10 — Cross-Goal Profile Sync](#flow-10--cross-goal-profile-sync)
11. [Flow 11 — Audio-Visual Adaptive Content Delivery](#flow-11--audio-visual-adaptive-content-delivery)
12. [Flow 12 — SOLO Taxonomy Quiz Evaluation](#flow-12--solo-taxonomy-quiz-evaluation)

---

## Flow 1 — User Login / Logout

### User Story

> **As a** learner,
> **I want to** register a new account, log in with my credentials, and log out,
> **so that** my learning progress is saved to my personal account and I can securely access it across sessions.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `test_store_and_auth.py` | `TestAuthStore` (10 tests) | User creation, password hashing (bcrypt), password verification, duplicate detection, user deletion, disk persistence |
| `test_store_and_auth.py` | `TestAuthJWT` (5 tests) | JWT token creation, verification, different users get different tokens, invalid/tampered/expired tokens return `None` |
| `test_auth_api.py` | `TestRegisterEndpoint` (6 tests) | `POST /auth/register` — success, returns valid JWT, rejects short username/password, rejects duplicate (409), creates user in store |
| `test_auth_api.py` | `TestLoginEndpoint` (5 tests) | `POST /auth/login` — success, returns valid JWT, wrong password (401), nonexistent user (401), login after register |
| `test_auth_api.py` | `TestAuthMeEndpoint` (4 tests) | `GET /auth/me` — valid token returns username, invalid/no token (401) |
| `test_auth_api.py` | `TestFullAuthLifecycle` (1 test) | End-to-end: register → login → verify → create data → delete → verify gone |

**Run command:**
```bash
python -m pytest backend/tests/test_store_and_auth.py backend/tests/test_auth_api.py -v
```

### Streamlit Frontend Test Steps

#### 1.1 — Register a new account

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start the app (`streamlit run frontend/main.py`). Ensure backend is running. | App loads, shows the Onboarding page with a top bar |
| 2 | Click the **account icon** (top-right) → **Register** tab | Registration form shown with username, password, confirm password fields |
| 3 | Enter username < 3 chars, click **Register** | Error: "Username must be at least 3 characters." |
| 4 | Enter password < 6 chars, click **Register** | Error: "Password must be at least 6 characters." |
| 5 | Enter mismatched passwords, click **Register** | Error: "Passwords do not match." |
| 6 | Enter valid credentials (e.g., `testuser1` / `pass123456`), click **Register** | Dialog closes, user is logged in. Account icon shows "Signed in as **testuser1**" |
| 7 | Try registering with the same username | Error: "Username already exists. Please choose another." |

#### 1.2 — Log in and log out

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Click account icon → **Log-out** | App returns to logged-out state |
| 2 | Click account icon → **Login** tab, enter wrong password | Error: "Invalid username or password." |
| 3 | Enter correct credentials, click **Login** | User is logged in. Previous progress restored if any |
| 4 | Click account icon → **Log-out** | Onboarding page shown. Login dialog available again |

---

## Flow 2 — Onboarding (Persona, Resume, Goal, Skill Gap)

> This flow consolidates all onboarding sub-flows: persona selection, resume upload, goal setting, goal refinement, skill gap identification, retrieval grounding, and all-mastered handling.

### User Story

> **As a** new learner,
> **I want to** select my learning persona, optionally upload my resume, set a learning goal, and have the platform identify my skill gaps,
> **so that** I get a personalized learning path focused on my actual weaknesses.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `test_user_state.py` | `TestUserStateStore` (11 tests), `TestUserStateAPI` (8 tests) | Persona, resume PDF text, goals, and all session state persistence via user-state endpoints |
| `test_onboarding_api.py` | `TestExtractPdfText` (3 tests) | `POST /extract-pdf-text` — valid PDF, multi-page, missing file (422) |
| `test_onboarding_api.py` | `TestRefineGoalEndpoint` (4 tests) | `POST /refine-learning-goal` — success (mocked LLM), forwards learner_information, empty info, LLM failure (500) |
| `test_onboarding_api.py` | `TestIdentifySkillGapEndpoint` (6 tests) | `POST /identify-skill-gap-with-info` — mocked LLM, field validation, pre-existing skill requirements, goal_assessment in response, search_rag_manager wiring |
| `test_onboarding_api.py` | `TestCreateLearnerProfileEndpoint` (3 tests) | `POST /create-learner-profile-with-info` — creates profile with cognitive_status/learning_preferences/behavioral_patterns, stores when user_id provided |
| `test_onboarding_api.py` | `TestProfileRetrieval` (4 tests) | `GET /profile/{user_id}` — by goal_id, all profiles, 404 cases |
| `test_onboarding_api.py` | `TestEventLogging` (3 tests) | `POST /events/log` — logs events, multiple events, auto-timestamps |
| `test_store_and_auth.py` | `TestProfilePersistence` (7 tests) | Profile upsert, get, overwrite, multiple goals, disk persistence |
| `test_skill_gap_tools.py` | `TestCourseContentRetrievalTool` (6 tests) | Retrieval tool: formatted docs, category/lecture filters, no results, fallback |
| `test_skill_gap_tools.py` | `TestGoalAssessmentTool` (7 tests) | Vagueness detection, all-mastered detection, suggestions |
| `test_skill_gap_tools.py` | `TestGoalRefinementTool` (4 tests) | Refinement output, was_refined flag, unchanged detection |
| `test_skill_gap_schemas.py` | `TestGoalAssessmentSchema` (4 tests) | GoalAssessment defaults, all fields, SkillGaps with/without goal_assessment |
| `test_skill_gap_orchestrator.py` | `TestAutoRefinementLoop` (5 tests) | Vague goal triggers refinement, non-vague/all-mastered do not, max 1 retry, response includes assessment |

**Run command:**
```bash
python -m pytest backend/tests/test_user_state.py backend/tests/test_onboarding_api.py backend/tests/test_store_and_auth.py::TestProfilePersistence backend/tests/test_skill_gap_tools.py backend/tests/test_skill_gap_schemas.py backend/tests/test_skill_gap_orchestrator.py -v
```

### Streamlit Frontend Test Steps

#### 2.1 — Persona selection

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Log in. Onboarding page shows single-page layout: goal input, persona cards, resume upload, "Begin Learning" button | Five persona cards: "Hands-on Explorer", "Reflective Reader", "Visual Learner", "Conceptual Thinker", "Balanced Learner" |
| 2 | Click **"Select"** under **"Hands-on Explorer"** | Card highlights (blue border). Button changes to "Selected" |
| 3 | Click **"Select"** under **"Reflective Reader"** | "Reflective Reader" highlights, "Hands-on Explorer" deselects. `learner_information` contains persona FSLSM values |
| 4 | Log out, log back in | Persona selection restored from backend |
| 5 | Click **"Begin Learning"** without selecting a persona | Warning: "Please provide both a learning goal and select a learning persona before continuing." |

#### 2.2 — Resume upload (optional)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Click upload area, select a valid PDF | Spinner: "Extracting text from PDF...". Toast: "PDF uploaded successfully." |
| 2 | Check `learner_information` (debug sidebar) | Extracted PDF text appended after persona prefix |
| 3 | Upload a non-PDF file | File uploader rejects it — only `.pdf` accepted |
| 4 | Skip PDF upload, click **"Begin Learning"** | Flow works normally — PDF is optional |
| 5 | Click **"Connect LinkedIn"** | Toast: "LinkedIn integration coming soon!" |

#### 2.3 — Setting a learning goal

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Observe the goal input field | Text input with placeholder "eg : learn english, python, data ....." |
| 2 | Leave goal empty, click **"Begin Learning"** | Warning: "Please provide both a learning goal and select a learning persona before continuing." |
| 3 | Enter a goal (e.g., "I want to become an HR Manager with expertise in HRIS systems"), select a persona, click **"Begin Learning"** | App navigates to the **Skill Gap** page. Spinner: "Identifying Skill Gap ..." |

#### 2.4 — Automatic goal refinement

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enter a vague goal (e.g., "learn stuff"), click **"Begin Learning"** | System auto-refines during skill gap identification |
| 2 | Observe the Skill Gap page | Info banner: "Your goal was automatically refined for better results." showing original and refined goals |
| 3 | Enter a goal that remains vague after refinement | Warning banner: "Your goal may be too vague to produce optimal results." with suggestion |
| 4 | Enter a specific goal (e.g., "Learn Python for data analysis with Pandas and Matplotlib") | No refinement occurs, no banner. Skills identified directly |

#### 2.5 — Skill gap identification and editing

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Wait for skill gap identification to complete | List of skills shown with: name, required level, current level, gap status (red/green header), reason, confidence |
| 2 | Verify summary text | Info banner: "There are X skills in total, with Y skill gaps identified." |
| 3 | Change a skill's **Current Level** from "beginner" to "advanced" (higher than required) | Header turns green. Gap toggle auto-disables. State saves |
| 4 | Change a skill's **Required Level** higher than current | Header turns red. Skill marked as gap |
| 5 | Toggle **"Mark as Gap"** off on a gap skill | Gap removed, current level set to match required |
| 6 | Verify resume influence (if uploaded) | Skills from your resume should show higher current levels |

#### 2.6 — Retrieval-grounded skill gaps (verified course content)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set a goal matching a verified course (e.g., "Introduction to Computer Science and Programming in Python") | Skills identified are grounded in course syllabus (e.g., "Variables and Types", "Control Flow") |
| 2 | Set a goal referencing specific content (e.g., "topics from lecture 3") | Skills grounded in that lecture's content |
| 3 | Set a goal NOT matching any course (e.g., "Learn Kubernetes cluster management") | Skills identified via LLM knowledge (fallback). No error |

#### 2.7 — All skills mastered handling

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set up a scenario where learner is expert in all required skills | Skill gap identification completes |
| 2 | Observe the Skill Gap page | Info banner: "You already master all required skills for this goal." **"Schedule Learning Path"** button is **disabled** |
| 3 | Click **"Edit Goal"** | Navigates back to onboarding |
| 4 | Manually lower a skill's current level (create a gap) | **"Schedule Learning Path"** becomes **enabled** |

#### 2.8 — Profile creation and scheduling

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Click **"Schedule Learning Path"** | Spinner: "Creating your profile ...". Toast: "Your profile has been created!". Navigates to **Learning Path** page |
| 2 | Navigate to **My Profile** | Profile shows: cognitive status, FSLSM dimensions matching persona, behavioral patterns |
| 3 | Navigate to **Dashboard** | Radar chart with 5-level axis. Required and current level traces plotted correctly |

---

## Flow 3 — User Account Deletion

### User Story

> **As a** user who no longer wants to use the platform,
> **I want to** permanently delete my account and all associated data,
> **so that** my personal information, learning history, and profile are completely removed from the system.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `test_auth_api.py` | `TestDeleteAccountEndpoint` (7 tests) | `DELETE /auth/user` — success (200), removes user from auth store, removes all data, preserves other users, rejects invalid/no token (401), login fails after deletion |
| `test_store_and_auth.py` | `TestDeleteAllUserData` (3 tests) | `delete_all_user_data()` — removes profiles, events, user state; preserves other users |

**Run command:**
```bash
python -m pytest backend/tests/test_auth_api.py::TestDeleteAccountEndpoint backend/tests/test_store_and_auth.py::TestDeleteAllUserData -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Log in with an account that has learning data. Navigate to **My Profile** | Profile page with "Delete Account" button at bottom |
| 2 | Click **"Delete Account"** | Confirmation dialog: "This action is permanent..." with **Delete** and **Cancel** |
| 3 | Click **Cancel** | Dialog closes. Account unchanged |
| 4 | Click **"Delete Account"** → **Delete** | Success: "Account deleted successfully." Redirects to logged-out state |
| 5 | Try logging in with deleted credentials | Error: "Invalid username or password." |
| 6 | Register with the same username | Succeeds. New account starts fresh — no old data |

---

## Flow 4 — Behavioral Patterns Display (Real Metrics)

### User Story

> **As a** learner viewing my profile,
> **I want to** see real metrics about my learning behavior (session count, average duration, total time, motivational triggers, mastery progress),
> **so that** I can understand my actual learning patterns rather than seeing generic AI-generated descriptions.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `test_behavioral_metrics.py` | `TestBehavioralMetrics` (7 tests) | `GET /behavioral-metrics/{user_id}` — 404 on missing user, zero metrics, session duration computation, goal filtering, trigger counting, mastery history, sessions learned count |

**Run command:**
```bash
python -m pytest backend/tests/test_behavioral_metrics.py -v
```

### Streamlit Frontend Test Steps

#### 4.1 — Fresh profile (no sessions completed)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete onboarding, navigate to **My Profile** | Profile page loads |
| 2 | Check **Session Completion** | Progress bar at 0%. Caption: "0 of N sessions completed" |
| 3 | Check **Session Duration & Engagement** | Info: "No completed sessions yet." |
| 4 | Check **Motivational Triggers** | Info: "No data yet." |
| 5 | Check **Mastery Progress** | Info: "No mastery data yet." |

#### 4.2 — After completing sessions

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete a session, navigate to **My Profile** | Sessions Completed shows 1. Avg Duration and Total Time displayed |
| 2 | Complete a second session (spend 4+ min for motivational triggers) | Sessions Completed: 2. Triggers count increases |

#### 4.3 — Backend unavailable (fallback)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Stop the backend server, navigate to **My Profile** | Behavioral patterns falls back to LLM-generated text |

---

## Flow 5 — Knowledge Content with Verified Course Materials

### User Story

> **As a** learner studying a topic covered by verified course materials,
> **I want** the learning content to be sourced from curated university materials first,
> **so that** I receive accurate, high-quality educational content rather than unreliable web search results.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `test_verified_content.py` | `TestVerifiedContentLoader` (8 tests) | Course scanning, file loading (JSON, text, unsupported), metadata, lecture number extraction |
| `test_verified_content.py` | `TestVerifiedContentManager` (5 tests) | Indexing, retrieval, dedup, empty collection, course listing |
| `test_verified_content.py` | `TestHybridRetrieval` (4 tests) | Verified-first cascade, web fallback, no VCM fallback, source type preservation |

**Run command:**
```bash
python -m pytest backend/tests/test_verified_content.py -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set a goal matching a verified course (e.g., "Introduction to Computer Science and Programming in Python"). Complete onboarding, schedule path, start a session | Content is generated |
| 2 | Observe the learning document | Content incorporates course material. Inline `[N]` citations. **References** section lists verified sources (e.g., "MIT 6.0001 — Lecture 8, p.3") |
| 3 | Set a goal NOT matching any course (e.g., "Learn Kubernetes"). Generate content | Inline citations present. **References** lists web search sources |

---

## Flow 6 — FSLSM-Driven Learning Path and Content Adaptations

### User Story

> **As a** learner with a specific learning style (FSLSM profile),
> **I want** the learning path structure and the content of each session to adapt based on my FSLSM dimensions,
> **so that** sessions include appropriate challenges, reflection time, sequencing, navigation, and content formatting suited to how I learn best.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `test_fslsm_overrides.py` | `TestFSLSMOverrides` (12 tests) | Deterministic FSLSM post-processing: checkpoint challenges, thinking time buffers, sequencing hints, navigation mode, mastery thresholds, combined dimensions, neutral defaults |
| `test_adaptive_content_delivery.py` | `TestFSLSMHints` (16 tests) | Processing, perception, and understanding dimension hint injection into content prompts |

**Run command:**
```bash
python -m pytest backend/tests/test_fslsm_overrides.py backend/tests/test_adaptive_content_delivery.py -v
```

### Streamlit Frontend Test Steps

> **Setup for each sub-test:** Select the specified persona, complete onboarding, and schedule a learning path.

#### 6.1 — Processing dimension: Active vs. Reflective

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select **"Hands-on Explorer"** (processing = -0.7, active). Schedule path | Session cards show caption: "Contains Checkpoint Challenges". `has_checkpoint_challenges = True` |
| 2 | Select **"Reflective Reader"** (processing = 0.7, reflective). Schedule path | Session cards show caption: "Recommended reflection time: 10 min". `thinking_time_buffer_minutes = 10` |

#### 6.2 — Perception dimension: Sensing vs. Intuitive

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select **"Hands-on Explorer"** (perception = -0.5, sensing). Schedule path | Session details show "Sequence: Application first". `session_sequence_hint = "application-first"` |
| 2 | Select **"Conceptual Thinker"** (perception = 0.7, intuitive). Schedule path | Session details show "Sequence: Theory first". `session_sequence_hint = "theory-first"` |

#### 6.3 — Input dimension: Visual vs. Verbal

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select **"Visual Learner"** (input = -0.8, visual). Schedule path | A **Module Map** (directed graph) appears on the Learning Path page. Nodes colored by status (green/blue/gray/white). Arrows show session order |
| 2 | Select **"Reflective Reader"** (input = 0.7, verbal). Schedule path | Module Map does NOT appear. A **Narrative Overview** section appears instead — sessions framed as "chapters" |

#### 6.4 — Understanding dimension: Sequential vs. Global

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select a sequential persona (e.g., "Reflective Reader", understanding = 0.5). Schedule path | `navigation_mode = "linear"`. Sessions 2+ locked until previous is mastered |
| 2 | Select **"Conceptual Thinker"** (understanding = 0.7, global). Schedule path | `navigation_mode = "free"`. All sessions navigable. Can open Session 3 without completing 1 or 2 |

#### 6.5 — Dual progress bars

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to the **Learning Path** page (any persona) | Two progress bars: "Sessions Completed" and "Sessions Mastered" |
| 2 | Complete a session without passing quiz | "Sessions Completed" increments, "Sessions Mastered" does not |
| 3 | Pass the quiz | "Sessions Mastered" increments |

#### 6.6 — FSLSM content-level hints (Sprint 3 — tight integration)

> These affect the **document content**, not path structure. All changes appear in the rendered markdown.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select **"Hands-on Explorer"** (processing = -0.7, active). Generate session content | Document contains a **🔧 Try It First** challenge block before the main explanation |
| 2 | Select **"Reflective Reader"** (processing = 0.7, reflective). Generate session content | Document contains a **🤔 Reflection Pause** deep-thinking question |
| 3 | Select **"Hands-on Explorer"** (perception = -0.5, sensing). Generate session content | Content begins with a concrete example before introducing theory |
| 4 | Select **"Conceptual Thinker"** (perception = 0.7, intuitive). Generate session content | Content begins with the abstract principle, then moves to examples |
| 5 | Select **"Reflective Reader"** (understanding = 0.5, sequential). Generate session content | Document sections follow strict linear order with explicit "Next, …" transitions |
| 6 | Select **"Conceptual Thinker"** (understanding = 0.7, global). Generate session content | Document opens with a **🗺️ Big Picture** overview section and cross-references between concepts |

---

## Flow 7 — Mastery Lock and Quiz-Based Mastery Evaluation

### User Story

> **As a** sequential learner,
> **I want** the system to evaluate my mastery via quiz scores and lock subsequent sessions until I demonstrate mastery,
> **so that** I build a solid foundation before moving to more advanced topics.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `test_quiz_scorer.py` | `TestComputeQuizScore` (11 tests) | Quiz scoring: all question types, edge cases (empty, None, partial) |
| `test_quiz_scorer.py` | `TestGetMasteryThreshold` (5 tests) | Threshold lookup: beginner (60%), expert (90%), mixed proficiency, defaults |
| `test_mastery_evaluation.py` | `TestMasteryEvaluation` (7 tests) | End-to-end: pass/fail, boundary, proficiency-based thresholds, fallback |

**Run command:**
```bash
python -m pytest backend/tests/test_quiz_scorer.py backend/tests/test_mastery_evaluation.py -v
```

### Streamlit Frontend Test Steps

#### 7.1 — Quiz submission and results

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to a session's knowledge document | Quiz section visible: radio buttons (single choice), checkboxes (multiple choice), radio (true/false), text input (short answer) |
| 2 | Answer some questions, click **"Submit Quiz"** | Score and mastery result displayed |
| 3 | Passing score | Success: "You scored X%! Mastery achieved (threshold: Y%)." Explanations shown |
| 4 | Failing score | Warning: "You scored X%. Mastery requires Y%." **"Retake Quiz"** button appears |
| 5 | Click **"Retake Quiz"** | Answers cleared. Quiz shown again |

#### 7.2 — Sequential mastery lock (linear navigation)

> **Prerequisite:** Select a sequential persona (e.g., "Reflective Reader") so `navigation_mode = "linear"`.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to Learning Path page | Session 1 has "Learning" button. Sessions 2+ show **disabled "Locked"** button with lock icon. Caption: "Master the previous session first" |
| 2 | Open Session 1, observe "Complete Session" button BEFORE quiz | Button is **disabled**. Info: "Pass the quiz to unlock session completion" |
| 3 | Submit quiz with passing score | "Complete Session" becomes **enabled** |
| 4 | Click **"Complete Session"** | Session marked as completed. Navigate to Learning Path: Session 1 shows green mastery badge. Session 2 unlocked |
| 5 | Complete and master all sessions sequentially | All session cards show mastery badges. No sessions locked |

#### 7.3 — No mastery lock for global learner

> **Prerequisite:** Select "Conceptual Thinker" (global → `navigation_mode = "free"`). See also Flow 6.4.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Open Session 3 without completing Sessions 1 or 2 | Session opens normally |
| 2 | Observe "Complete Session" in knowledge document | Button always enabled — not gated behind quiz mastery |

#### 7.4 — Mastery score badges

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Pass a quiz, navigate to Learning Path | Session card shows green badge: "Mastered: X%" |
| 2 | Fail a quiz, navigate to Learning Path | Session card shows warning badge: "Quiz score: X% (need Y%)" |
| 3 | Session with no quiz attempted | No mastery badge shown |

#### 7.5 — Proficiency-based mastery thresholds

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Score 60% on a beginner-level session | Mastery achieved (threshold: 60%) |
| 2 | Score 70% on an advanced-level session | Mastery NOT achieved (threshold: 80%). Must retake |
| 3 | Retake and score 85% | Mastery achieved (85 >= 80) |

#### 7.6 — Semantic short-answer evaluation (Sprint 3)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Submit a short-answer response that is correct but differently worded (e.g., "A programming language" for "Python") | Marked correct. Feedback explains why the answer is accepted |
| 2 | Submit a response with entirely wrong meaning | Marked incorrect. Feedback explains the expected concept |
| 3 | Click **"View Explanations"** after submission | Each short-answer shows expected answer plus the semantic evaluation feedback in green (correct) or red (incorrect) |

#### 7.7 — SOLO-aligned quiz mix per proficiency (Sprint 3)

> See also Flow 12 for full SOLO quiz evaluation details.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to a **beginner**-level session quiz | Quiz contains: 4 single-choice + 1 true/false. No multiple-choice, short-answer, or open-ended questions |
| 2 | Navigate to an **intermediate**-level session quiz | Quiz contains: 2 single-choice + 2 multiple-choice + 1 true/false |
| 3 | Navigate to an **advanced**-level session quiz | Quiz contains: 1 single-choice + 1 multiple-choice + 2 short-answer + 1 open-ended |
| 4 | Navigate to an **expert**-level session quiz | Quiz contains: 1 multiple-choice + 1 short-answer + 3 open-ended |

---

## Flow 8 — Agentic Learning Plan Generation

### User Story

> **As a** learner who has completed skill gap identification,
> **I want** the system to automatically generate a high-quality learning path, evaluate it, and refine it if needed — without any manual intervention,
> **so that** I receive a well-structured, personalized learning plan that has been quality-checked.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `test_agentic_learning_plan.py` | `TestLearningPathSchedulerInit` (1 test) | Scheduler initialization without tools |
| `test_agentic_learning_plan.py` | `TestAgenticMetadata` (4 tests) | Quality gate keys, scheduler without tools, max refinement cap |
| `test_plan_quality_gate.py` | `TestEvaluatePlanQuality` (7 tests) | Deterministic quality gate: positive/negative feedback, issue extraction, suggestion count threshold |

**Run command:**
```bash
python -m pytest backend/tests/test_agentic_learning_plan.py backend/tests/test_plan_quality_gate.py -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete skill gap identification, click **"Schedule Learning Path"** | Spinner: "Generating your personalized learning plan...". Learning path loads with session cards |
| 2 | Check session topics | Sessions cover the skill gaps. Ordering is logical and progressive |
| 3 | Verify no manual refinement buttons | No "Simulate Feedback", "Refine Path", or "Auto-Refine" buttons exist — refinement is automatic |
| 4 | Observe the **Plan Quality** section | Shows "PASS" (green) or "NEEDS REVIEW" (orange). Three scores: Progression, Engagement, Personalization. Refinement iterations count displayed |
| 5 | If quality is "NEEDS REVIEW" | Issues list displayed below the scores |

---

## Flow 9 — Adaptive Plan Regeneration

### User Story

> **As a** learner whose learning preferences have changed or who has failed to achieve mastery in a session,
> **I want** the system to detect these changes and suggest adapting my learning path,
> **so that** my plan stays aligned with my evolving needs while preserving the progress I've already made.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `test_plan_regeneration.py` | `TestComputeFSLSMDeltas` (2 tests) | FSLSM delta computation, handles missing dimensions |
| `test_plan_regeneration.py` | `TestCountMasteryFailures` (2 tests) | Mastery failure counting, empty results |
| `test_plan_regeneration.py` | `TestDecideRegeneration` (9 tests) | Decision logic: keep (delta < 0.3), adjust_future (delta in [0.3, 0.5) or single mastery failure), regenerate (delta >= 0.5 or sign flip or multiple failures), preserves learned sessions |

**Run command:**
```bash
python -m pytest backend/tests/test_plan_regeneration.py -v
```

### Streamlit Frontend Test Steps

#### 9.1 — Adaptation decision scenarios

> Test all three decision outcomes by varying the triggering condition.

| Scenario | Trigger | Expected Decision |
|----------|---------|-------------------|
| Minor preference change (delta < 0.3) | Small FSLSM tweak within same persona | **KEEP** — "Your current plan is still on track." No changes made |
| Moderate preference change (delta 0.3–0.5) | Moderate FSLSM shift on one dimension | **ADJUST_FUTURE** — Future sessions adjusted. Shows which sessions affected |
| Major preference change (delta >= 0.5 or sign flip) | Switch from "Hands-on Explorer" to "Conceptual Thinker" | **REGENERATE** — Plan regenerated. Full reasoning shown |
| Single mastery failure | Score significantly below threshold (e.g., 30% vs 70%) | **ADJUST_FUTURE** — Future sessions adjusted to reinforce weak areas |

For each scenario:

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Trigger the condition (preference change or mastery failure) | Adaptation banner appears on Learning Path page with **"Adapt Learning Path"** button |
| 2 | Click **"Adapt Learning Path"** | Spinner while processing. Decision and reasoning displayed |
| 3 | Verify learned sessions preserved (if REGENERATE) | Previously completed sessions retain "learned" status, mastery scores, and content. Only unlearned sessions change |

---

## Flow 10 — Cross-Goal Profile Sync

### User Story

> **As a** learner with multiple learning goals,
> **I want** my mastered skills and learning preferences to carry across all goals,
> **so that** new goals recognize what I already know and my learning style is consistent.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `test_profile_sync.py` | `TestMergeSharedProfileFields` (8 tests) | Mastered skills union (highest proficiency wins), FSLSM propagation, behavioral patterns propagation, in_progress cleanup, overall_progress recalculation, persistence, no-op when single goal |
| `test_profile_sync.py` | `TestSyncEndpoint` (2 tests) | POST /sync-profile returns merged profile, 404 when no profile exists |

**Run command:**
```bash
python -m pytest backend/tests/test_profile_sync.py -v
```

### Streamlit Frontend Test Steps

#### 10.1 — New goal inherits mastered skills

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete onboarding for Goal A (e.g., "Learn Python"). Complete sessions until a skill is mastered | Skill appears in mastered_skills on My Profile |
| 2 | Create a new Goal B (e.g., "Learn Kubernetes") | Onboarding flow starts |
| 3 | On the Skill Gap page, observe the identified gaps | Skills mastered in Goal A are NOT listed as gaps |
| 4 | Click "Schedule Learning Path" | Profile is created and synced |
| 5 | Navigate to My Profile for Goal B | Mastered skills from Goal A appear in Goal B's mastered_skills list |

#### 10.2 — FSLSM preferences shared across goals

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | On Goal A's My Profile, update preferences (e.g., "I prefer visual learning") | FSLSM dimensions update |
| 2 | Switch to Goal B via the goal selector | Goal B becomes active |
| 3 | Navigate to My Profile for Goal B | Same FSLSM dimension values as Goal A |

#### 10.3 — Goal switch syncs mastered skills

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | With two active goals, complete a session in Goal A that masters a skill | Skill moves to mastered_skills in Goal A |
| 2 | Switch to Goal B | Profile sync runs |
| 3 | Navigate to My Profile for Goal B | Newly mastered skill from Goal A appears. If Goal B had the same skill in in_progress, it's now gone |

#### 10.4 — First goal (no other goals to sync from)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Fresh user, create first goal | Profile is created normally. No errors from sync |

---

## Flow 11 — Audio-Visual Adaptive Content Delivery

### User Story

> **As a** visual or auditory learner,
> **I want** the learning content to be delivered in a format that matches my sensory preference (diagrams and videos for visual learners; podcast-style dialogue and an audio player for auditory learners),
> **so that** I absorb information more effectively through my preferred modality.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `test_adaptive_content_delivery.py` | `TestMediaResourceFinder` (6 tests) | YouTube video ID extraction, thumbnail URL, Wikipedia image retrieval, deduplication, exception handling |
| `test_adaptive_content_delivery.py` | `TestVisualFormattingHints` (5 tests) | Hint injection for strong/moderate visual learners, no-op for standard and auditory |
| `test_adaptive_content_delivery.py` | `TestPodcastStyleConverter` (4 tests) | Rich-text narrative rewrite (moderate auditory), Host-Expert dialogue (strong auditory) |
| `test_adaptive_content_delivery.py` | `TestTTSGenerator` (6 tests) | Markdown stripping, dialogue turn parsing, dual-voice MP3 generation, audio URL format |
| `test_adaptive_content_delivery.py` | `TestContentFormatField` (4 tests) | `content_format` value: standard / visual_enhanced / podcast |
| `test_adaptive_content_delivery.py` | `TestAudioURL` (4 tests) | `audio_url` present for strong auditory, absent otherwise |

**Run command:**
```bash
python -m pytest backend/tests/test_adaptive_content_delivery.py -v
```

### Streamlit Frontend Test Steps

#### 11.1 — Strong visual learner (fslsm_input ≤ -0.7)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select **"Visual Learner"** persona, complete onboarding, generate session content | Stage 3 spinner completes. Info banner: "📊 This content includes visual resources (diagrams, videos, images) for visual learners." |
| 2 | Read through the document sections | Document contains Mermaid diagrams and/or tables in the body. A "📺 Visual Learning Resources" section appears with YouTube thumbnails and Wikipedia image links |
| 3 | Click a YouTube thumbnail link | Opens YouTube video in a new tab |

#### 11.2 — Moderate visual learner (-0.7 to -0.3)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select a persona with input score around -0.5. Generate session content | Info banner shown. Document may contain a table or diagram. One YouTube video link in resources section |

#### 11.3 — Standard learner (-0.3 to +0.3)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select **"Balanced Learner"** persona. Generate session content | No info banner displayed. Document format unchanged. No audio player |

#### 11.4 — Moderate auditory learner (+0.3 to +0.7)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select a persona with input score around +0.5. Generate session content | Info banner: "🎙️ This content has been adapted into a podcast-style format for auditory learners." |
| 2 | Read the document | Document is written in a rich first-person narrative with analogies and vivid metaphors. No audio player (TTS not triggered at this level) |

#### 11.5 — Strong auditory learner (fslsm_input ≥ +0.7)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select **"Reflective Reader"** persona (input = 0.7). Generate session content | Info banner: "🎙️ This content has been adapted into a podcast-style format for auditory learners." |
| 2 | Observe the audio player below the banner | An audio player (`st.audio`) is displayed. Clicking play streams the dual-voice MP3 |
| 3 | Read the document | Document begins with "# 🎧 [Podcast] …" title. Body shows alternating `**[HOST]**:` and `**[EXPERT]**:` dialogue turns |
| 4 | Navigate to the next document section | Audio player remains accessible (shown above the section content) |

#### 11.6 — TTS failure fallback

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Backend TTS generation fails (e.g., network error). Generate content for strong auditory learner | Info banner still shown. No audio player displayed (audio_url absent). Podcast-format text still rendered |

---

## Flow 12 — SOLO Taxonomy Quiz Evaluation

### User Story

> **As a** learner completing a session quiz,
> **I want** the quiz question types to match my proficiency level and receive qualitative SOLO-taxonomy feedback on my open-ended and short-answer responses,
> **so that** I understand not just whether I was right or wrong, but the depth of my understanding.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `test_quiz_mix.py` | `TestQuizMixByProficiency` (6 tests) | Graduated question counts for beginner / intermediate / advanced / expert / mixed proficiency / empty outcomes |
| `test_solo_evaluator.py` | `TestSOLOEvaluation` (6 tests) | SOLO level classification, fractional score, qualitative feedback for all 5 levels |
| `test_quiz_scorer.py` | `TestHybridScoring` (4 tests) | Open-ended fractional scores + LLM short-answer results merged with deterministic scoring |

**Run command:**
```bash
python -m pytest backend/tests/test_quiz_mix.py backend/tests/test_solo_evaluator.py backend/tests/test_quiz_scorer.py -v
```

### Streamlit Frontend Test Steps

#### 12.1 — Graduated question mix

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete onboarding with a **beginner**-level goal. Generate session content, reach the quiz | Quiz shows exactly 4 single-choice + 1 true/false. No short-answer or open-ended questions visible |
| 2 | Complete onboarding with an **expert**-level goal. Reach the quiz | Quiz shows 1 multiple-choice + 1 short-answer + 3 open-ended. No single-choice or true/false |
| 3 | Complete onboarding with an **intermediate**-level goal. Reach the quiz | Quiz shows 2 single-choice + 2 multiple-choice + 1 true/false |
| 4 | Complete onboarding with an **advanced**-level goal. Reach the quiz | Quiz shows 1 single-choice + 1 multiple-choice + 2 short-answer + 1 open-ended |

#### 12.2 — Open-ended question rendering

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Reach an expert or advanced session quiz with open-ended questions | Each open-ended question shows: question text, caption "Write a detailed response demonstrating your understanding.", large text area (150 px tall) |
| 2 | Type a multi-paragraph response into the text area | Text area accepts all input. Content preserved on next rerun |
| 3 | Leave an open-ended answer blank and click **"Submit Quiz"** | Blank answer treated as no response (prestructural) — scored 0 |

#### 12.3 — SOLO-level feedback after submission

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Submit quiz with open-ended responses | Spinner: "Evaluating your responses…" for ~3–8 seconds (LLM evaluation) |
| 2 | After result, click **"View Explanations"** | Open-ended section shows: rubric text, example answer, SOLO level in color-coded text, percentage score, qualitative feedback |
| 3 | Submit a response demonstrating Extended Abstract thinking | Green "Extended Abstract" label, score 100% |
| 4 | Submit a response mentioning only one relevant concept | Orange "Unistructural" label, score 25% |
| 5 | Submit a completely irrelevant or blank response | Red "Prestructural" label, score 0% |
| 6 | Submit a response integrating multiple concepts | Blue "Relational" label, score 75% |

#### 12.4 — Short-answer semantic evaluation

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Answer a short-answer question with a correct but differently worded response | After submission, "View Explanations" shows green ✓ with semantic feedback |
| 2 | Answer with completely wrong meaning | Red ✗ with explanation of expected concept |

#### 12.5 — Mastery score with open-ended

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Expert session: answer all questions well (Relational-level open-ended) | Score includes fractional SOLO score. Mastery achieved if total ≥ threshold |
| 2 | Expert session: answer open-ended at Prestructural level | Open-ended contributes 0 to score. Overall score drops proportionally |

#### 12.6 — Backward compatibility

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Load a cached quiz generated before Sprint 3 (4 question types only, no open_ended key) | Quiz renders normally. No errors. Open-ended section not displayed |
| 2 | Submit the legacy quiz | Scoring works. `open_ended_feedback` absent (empty list). No UI errors |

---

## Test Coverage Summary

### Backend Test Files

| File | Tests | Flows Covered |
|---|---|---|
| `test_store_and_auth.py` | 33 | Flow 1 (auth), Flow 2 (profile persistence), Flow 3 (data deletion) |
| `test_user_state.py` | 19 | Flow 2 (persona, resume, goal persistence) |
| `test_auth_api.py` | 23 | Flow 1 (register/login/me), Flow 3 (delete account + lifecycle) |
| `test_onboarding_api.py` | 36 | Flow 2 (PDF extract, goal refinement, skill gap, profile creation, events) |
| `test_skill_gap_tools.py` | 17 | Flow 2 (retrieval tool, goal assessment, goal refinement) |
| `test_skill_gap_schemas.py` | 4 | Flow 2 (GoalAssessment schema) |
| `test_skill_gap_orchestrator.py` | 5 | Flow 2 (auto-refinement loop) |
| `test_fslsm_update.py` | 2 | Flow 2 (FSLSM dimension updates — integration test, requires LLM API key) |
| `test_behavioral_metrics.py` | 7 | Flow 4 (behavioral metrics) |
| `test_verified_content.py` | 17 | Flow 5 (verified content loading, indexing, retrieval) |
| `test_fslsm_overrides.py` | 12 | Flow 6 (FSLSM path-level adaptations) |
| `test_quiz_scorer.py` | 16 | Flow 7, Flow 12 (quiz scoring, mastery thresholds, hybrid SOLO scoring) |
| `test_mastery_evaluation.py` | 7 | Flow 7 (mastery evaluation) |
| `test_agentic_learning_plan.py` | 5 | Flow 8 (agentic plan generation) |
| `test_plan_quality_gate.py` | 7 | Flow 8 (quality gate) |
| `test_plan_regeneration.py` | 13 | Flow 9 (adaptive regeneration) |
| `test_profile_sync.py` | 10 | Flow 10 (cross-goal profile sync) |
| `test_adaptive_content_delivery.py` | 45 | Flow 6 (FSLSM content hints), Flow 11 (audio-visual delivery) |
| `test_solo_evaluator.py` | 6 | Flow 12 (SOLO level classification, semantic short-answer evaluation) |
| `test_quiz_mix.py` | 6 | Flow 12 (graduated question mix by proficiency) |
| **Total** | **315** | |

### Running All Tests

```bash
# All tests (no LLM API key required except test_fslsm_update.py and test_solo_evaluator.py):
python -m pytest backend/tests/ -v

# Sprint 3 tests only (audio-visual delivery + SOLO quizzes):
python -m pytest backend/tests/test_adaptive_content_delivery.py backend/tests/test_quiz_mix.py backend/tests/test_solo_evaluator.py -v

# Integration tests only (require LLM API key):
python -m pytest backend/tests/test_fslsm_update.py backend/tests/test_solo_evaluator.py -v
```

---

### Notes for the Team

1. **API endpoint tests** (`test_auth_api.py`, `test_onboarding_api.py`, `test_user_state.py` API section) require the full backend dependency stack (langchain, etc.) because they import `from main import app`. Run these in the dev environment with all backend dependencies installed.

2. **LLM-dependent endpoint tests** (`test_onboarding_api.py`) use **mocked LLM functions** — they do NOT call real LLM APIs. This means they test the endpoint contract (request/response shapes, error handling, store persistence) without needing API keys.

3. **Integration tests** (`test_fslsm_update.py`) call real LLMs and require an OpenAI API key configured in the environment.

4. **Frontend tests** are manual — Streamlit does not have a built-in automated testing framework. Follow the step-by-step tables above, checking each expected result. Document any deviations as bugs.

5. **Configuration endpoints** — The backend exposes two read-only configuration endpoints that the frontend (Streamlit or React) fetches at startup. These do not require authentication:
   - `GET /personas` — Returns the learning persona definitions (names, descriptions, FSLSM dimension values).
   - `GET /config` — Returns application configuration: skill levels, default session count, default LLM type/method, FSLSM threshold values and labels, motivational trigger interval, and max refinement iterations. The frontend falls back to local defaults if the backend is unreachable.
