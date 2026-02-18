# API Impact of Agentic Improvements

How the API endpoints and frontend-backend interaction patterns would change for each agentic proposal.

---

## The Core Problem: Sync REST vs. Autonomous Agents

The current architecture is **synchronous request-response**:

```
Frontend (Streamlit)                    Backend (FastAPI)
        │                                      │
        ├── POST /identify-skill-gap ──────►   │ (blocks 5-15s)
        │◄──────────── JSON response ──────────┤
        │                                      │
        ├── POST /schedule-learning-path ──►   │ (blocks 5-15s)
        │◄──────────── JSON response ──────────┤
```

Every action is initiated by the frontend. The backend never acts on its own. Making agents autonomous breaks this model in three ways:

1. **Longer execution times** — an agent that self-refines makes 3-5 LLM calls instead of 1
2. **Backend-initiated actions** — an event-aware profile agent decides to act without a frontend request
3. **Multi-step interactions** — a skill gap agent that needs quiz answers must pause mid-execution and wait for user input

Each requires a different API pattern.

---

## Pattern 1: Async Jobs (for Self-Refining Agents)

**Affects:** Self-refining path scheduler, self-refining content generator

### Current API
```
POST /schedule-learning-path
  → blocks for 5-15s
  → returns { learning_path: [...] }
```

The frontend calls `httpx.post(..., timeout=500)` and waits.

### Problem
A self-refining scheduler that calls the feedback simulator 2-3 times takes 30-60s. The current sync model either times out or leaves the user staring at a spinner with no feedback.

### New API Pattern: Job Submission + Polling

```
POST /schedule-learning-path
  → returns immediately: { job_id: "abc123", status: "running" }

GET /jobs/{job_id}
  → returns: {
      status: "running" | "completed" | "failed",
      progress: {
        current_step: "Refining path based on feedback (iteration 2/3)",
        steps_completed: 3,
        steps_total: 5
      },
      result: null  (or the final learning_path when completed)
    }
```

**Backend implementation:**
```python
from fastapi import BackgroundTasks

jobs: Dict[str, Dict] = {}  # In production, use Redis

@app.post("/schedule-learning-path")
async def schedule_learning_path(request: ..., background_tasks: BackgroundTasks):
    job_id = str(uuid4())
    jobs[job_id] = {"status": "running", "progress": {}, "result": None}
    background_tasks.add_task(run_scheduling_job, job_id, request)
    return {"job_id": job_id, "status": "running"}

async def run_scheduling_job(job_id: str, request):
    # The agent decides how many iterations to run
    jobs[job_id]["progress"]["current_step"] = "Generating initial path"
    path = scheduler.schedule_session(...)

    jobs[job_id]["progress"]["current_step"] = "Simulating learner feedback"
    feedback = simulator.feedback_path(...)

    # Agent decides whether to refine
    if agent_judges_refinement_needed(feedback):
        jobs[job_id]["progress"]["current_step"] = "Refining path (iteration 1)"
        path = scheduler.reflexion(path, feedback)
        ...

    jobs[job_id]["status"] = "completed"
    jobs[job_id]["result"] = path
```

**Frontend change:**
```python
# Submit job
response = httpx.post("/schedule-learning-path", json=data)
job_id = response.json()["job_id"]

# Poll with progress display
with st.spinner("Generating learning path..."):
    while True:
        status = httpx.get(f"/jobs/{job_id}").json()
        if status["status"] == "completed":
            learning_path = status["result"]
            break
        st.text(status["progress"]["current_step"])  # Show what agent is doing
        time.sleep(2)
```

**Alternative: Server-Sent Events (SSE)**

Instead of polling, the backend streams progress updates:

```
POST /schedule-learning-path  → { job_id: "abc123" }
GET  /jobs/{job_id}/stream    → SSE stream:
  data: {"step": "Generating initial path"}
  data: {"step": "Simulating learner feedback"}
  data: {"step": "Feedback suggests adding remedial session, refining..."}
  data: {"step": "completed", "result": { learning_path: [...] }}
```

This gives the user real-time visibility into what the agent is doing and why — which is valuable for trust.

---

## Pattern 2: Event-Triggered Background Processing (for Autonomous Profile Updates)

**Affects:** Event-aware profile agent

### Current API

The frontend explicitly triggers profile updates at two points:
1. `update_learner_profile_with_additional_info()` — user manually submits new info on the profile page
2. `update_learner_profile_with_feedback()` — called when a session is completed or feedback is submitted

The backend's `POST /profile/auto-update` endpoint is available but the frontend doesn't use the event store — it passes feedback directly as `learner_interactions`.

### Problem
The profile agent has no autonomy. It only runs when the frontend explicitly calls it. If the user takes 5 quizzes, the frontend would need to decide after each one: "should I call profile update?" Currently it doesn't — it only updates on session completion.

### New API Pattern: Event Hook + Background Agent

**Option A: Inline evaluation on every event log**

```python
@app.post("/events/log")
async def log_event(evt: BehaviorEvent, background_tasks: BackgroundTasks):
    store.append_event(evt.user_id, evt.dict())

    # The profile agent decides whether to update — not the frontend
    background_tasks.add_task(
        maybe_update_profile, evt.user_id, evt.event_type
    )
    return {"ok": True}

async def maybe_update_profile(user_id: str, trigger_event_type: str):
    """Give the profile agent a tool to check events and decide."""
    profiler = AdaptiveLearnerProfiler(llm, tools=[check_event_log_tool])

    # The agent looks at the events and decides
    decision = profiler.invoke({
        "task": "evaluate_update_need",
        "user_id": user_id,
        "trigger": trigger_event_type,
    })

    if decision["should_update"]:
        # Agent runs the full profile update
        updated = profiler.update_profile(...)
        store.upsert_profile(user_id, goal_id, updated)

        # Notify the frontend that the profile changed
        notifications.push(user_id, {
            "type": "profile_updated",
            "reason": decision["reason"],
            "changes": decision["summary"],
        })
```

**The key insight:** The `POST /events/log` endpoint already exists and the frontend already calls it. The only change is that logging an event now *might* trigger a background profile update. The frontend doesn't need to know or care — it logs events as before, and occasionally gets notified that the profile changed.

**Option B: Periodic background worker**

```python
# Runs every N minutes via APScheduler, Celery Beat, or a simple asyncio task
async def periodic_profile_check():
    for user_id in store.get_active_users():
        events = store.get_events(user_id)
        last_update = store.get_last_profile_update_time(user_id)

        # Give the agent the event summary and let it decide
        profiler = AdaptiveLearnerProfiler(llm, tools=[check_event_log_tool])
        ...
```

**Frontend change — receiving push notifications:**

The frontend needs a way to know the profile was updated in the background. Options:

1. **Polling** (simplest): Frontend periodically calls `GET /profile/{user_id}?since={last_check_ts}` and refreshes if changed
2. **SSE** (better UX): Frontend subscribes to `GET /notifications/{user_id}/stream` and gets push updates
3. **WebSocket** (best for real-time): Bidirectional channel for all real-time updates

```python
# SSE approach — new endpoint
@app.get("/notifications/{user_id}/stream")
async def notification_stream(user_id: str):
    async def event_generator():
        while True:
            notification = await notification_queue.get(user_id)
            yield f"data: {json.dumps(notification)}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**Frontend (Streamlit) limitation:** Streamlit doesn't natively support SSE/WebSocket listeners within a page. Pragmatic workaround: use a short polling interval or an `st.experimental_fragment` that re-checks every 10s.

```python
# Streamlit polling approach
if "last_profile_check" not in st.session_state:
    st.session_state.last_profile_check = time.time()

if time.time() - st.session_state.last_profile_check > 10:
    latest_profile = httpx.get(f"/profile/{user_id}").json()
    if latest_profile != st.session_state.current_profile:
        st.toast("Your profile was updated based on recent activity")
        st.session_state.current_profile = latest_profile
    st.session_state.last_profile_check = time.time()
```

### What the user experiences

**Before (current):**
> User completes a session → clicks "Complete Session" → waits for profile update → sees new profile

**After (agentic):**
> User takes a quiz and scores poorly → continues browsing → a toast appears: "Your profile was updated: Data Analysis skill moved from multistructural to unistructural based on recent quiz performance" → user can view the updated profile whenever they want

The profile agent decided autonomously that a quiz failure was significant enough to warrant an update. No frontend button was pressed.

---

## Pattern 3: Multi-Step Interaction Sessions (for Skill Gap Assessment)

**Affects:** Skill gap identifier with assessment strategy selection

### Current API
```
POST /identify-skill-gap-with-info
  body: { learning_goal, learner_information }
  → returns: { skill_gaps: [...], skill_requirements: [...] }
```

One request, one response. The agent gets the resume and guesses all levels at once.

### Problem
The agentic skill gap identifier might decide: "I can infer Python level from the resume (high confidence), but I need a diagnostic quiz to determine the Machine Learning level (low confidence)." This requires **pausing the agent** to collect quiz answers from the user, then **resuming** to complete the assessment.

### New API Pattern: Assessment Sessions

```
POST /skill-gap/start-assessment
  body: { learning_goal, learner_information }
  → returns: {
      session_id: "assessment_abc123",
      status: "needs_input",
      completed_skills: [
        { name: "Python", level: "relational", confidence: "high", method: "resume" }
      ],
      pending_quiz: {
        skill: "Machine Learning",
        reason: "Resume mentions 'some experience' but no specific projects",
        questions: [
          {
            id: "q1",
            type: "single_choice",
            question: "Which of the following best describes the relationship between bias and variance in ML models?",
            options: ["A: ...", "B: ...", "C: ...", "D: ..."]
          },
          {
            id: "q2",
            type: "short_answer",
            question: "Describe a scenario where you would choose a random forest over logistic regression and explain why."
          }
        ]
      },
      remaining_skills: ["Data Visualization", "Statistical Analysis"]
    }

POST /skill-gap/submit-answers
  body: {
    session_id: "assessment_abc123",
    answers: { "q1": "C", "q2": "Random forests handle non-linear..." }
  }
  → returns: {
      session_id: "assessment_abc123",
      status: "needs_input" | "completed",
      completed_skills: [
        { name: "Python", level: "relational", confidence: "high", method: "resume" },
        { name: "Machine Learning", level: "multistructural", confidence: "high", method: "diagnostic_quiz" }
      ],
      pending_quiz: { ... } | null,   // Another quiz if needed, or null if done
      remaining_skills: [...]
    }

# If agent decided no more quizzes are needed:
  → returns: {
      session_id: "assessment_abc123",
      status: "completed",
      skill_gaps: [ ... ],   // Final result, same schema as current
      skill_requirements: [ ... ],
      assessment_summary: {
        skills_from_resume: 4,
        skills_from_quiz: 2,
        total_questions_asked: 4
      }
    }
```

**Backend implementation using LangGraph checkpointing:**
```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()

@app.post("/skill-gap/start-assessment")
async def start_assessment(request: ...):
    session_id = str(uuid4())

    # Create agent with tools + checkpointing
    identifier = SkillGapIdentifier(
        llm,
        tools=[analyze_resume_tool, generate_diagnostic_quiz_tool],
        checkpointer=checkpointer,
        interrupt_before=["generate_diagnostic_quiz"],  # Pause when quiz is needed
    )

    # Run until the agent hits the quiz tool (interrupt)
    result = identifier.invoke(
        {"learning_goal": ..., "learner_information": ...},
        config={"configurable": {"thread_id": session_id}}
    )

    # Agent is now paused, waiting for quiz answers
    return {
        "session_id": session_id,
        "status": "needs_input",
        "pending_quiz": result["pending_quiz"],
        "completed_skills": result["completed_skills"],
    }

@app.post("/skill-gap/submit-answers")
async def submit_answers(request: ...):
    # Resume the agent with the quiz answers
    result = identifier.invoke(
        {"quiz_answers": request.answers},
        config={"configurable": {"thread_id": request.session_id}}
    )

    if result.get("pending_quiz"):
        return {"status": "needs_input", "pending_quiz": result["pending_quiz"], ...}
    else:
        return {"status": "completed", "skill_gaps": result["skill_gaps"], ...}
```

**Frontend change:**
```python
# Start assessment
response = httpx.post("/skill-gap/start-assessment", json=data)
session = response.json()

while session["status"] == "needs_input":
    quiz = session["pending_quiz"]
    st.subheader(f"Quick assessment: {quiz['skill']}")
    st.caption(quiz["reason"])

    answers = {}
    for q in quiz["questions"]:
        if q["type"] == "single_choice":
            answers[q["id"]] = st.radio(q["question"], q["options"])
        elif q["type"] == "short_answer":
            answers[q["id"]] = st.text_area(q["question"])

    if st.button("Submit Answers"):
        response = httpx.post("/skill-gap/submit-answers", json={
            "session_id": session["session_id"],
            "answers": answers
        })
        session = response.json()

# Assessment complete
skill_gaps = session["skill_gaps"]
```

**What the user experiences:**

**Before (current):**
> User uploads resume → system guesses all skill levels → some have "low" confidence → user doesn't know which assessments are unreliable

**After (agentic):**
> User uploads resume → system says "I identified 6 skills. I'm confident about 4 from your resume, but I need to ask you 2-3 quick questions about Machine Learning and Data Visualization" → user answers a short targeted quiz → system returns all skill levels with high confidence → user trusts the result

---

## Pattern 4: Compound Endpoints (for Session Orchestrator)

**Affects:** Autonomous learning session orchestrator

### Current API

The frontend orchestrates the full learning loop across 4-5 separate endpoints:

```
Frontend calls:
  1. POST /schedule-learning-path
  2. POST /tailor-knowledge-content  (per session)
  3. POST /events/log               (quiz results, engagement)
  4. POST /profile/auto-update
  5. POST /reschedule-learning-path
```

The frontend decides the order, when to call each, and what to pass between them.

### New API Pattern: Single orchestrated endpoint

```
POST /learning/next-action
  body: {
    user_id: "user123",
    trigger: "session_completed",
    context: {
      completed_session_id: "Session 3",
      quiz_scores: [80, 60, 90],
      time_spent_minutes: 25,
      feedback: "The examples were helpful but too simple"
    }
  }
  → returns: {
      job_id: "orchestration_xyz",
      status: "running"
    }

GET /jobs/{job_id}
  → returns: {
      status: "completed",
      actions_taken: [
        { action: "profile_updated", detail: "Lowered 'Data Analysis' from relational to multistructural" },
        { action: "path_rescheduled", detail: "Inserted remedial session on data analysis" },
        { action: "content_generated", detail: "Created content for new Session 3b" }
      ],
      result: {
        updated_profile: { ... },
        updated_path: { ... },
        next_session_content: { ... }
      }
    }
```

The backend orchestrator agent decides autonomously:
- Whether to update the profile (yes, because quiz score was 60%)
- Whether to reschedule the path (yes, because a skill regressed)
- Whether to generate content for the next session (yes, because a new session was inserted)

**Frontend simplification:**

```python
# Before: 4-5 separate API calls with frontend logic
# After: 1 call, backend handles everything

response = httpx.post("/learning/next-action", json={
    "user_id": user_id,
    "trigger": "session_completed",
    "context": { ... }
})
job_id = response.json()["job_id"]

# Poll for result with progress display
result = await poll_job(job_id)

# Show what the system decided
for action in result["actions_taken"]:
    st.info(f"{action['action']}: {action['detail']}")
```

---

## Summary: API Changes by Proposal

| Proposal | API Pattern | New Endpoints | Frontend Change |
|----------|-------------|---------------|-----------------|
| 1. Self-refining path scheduler | Async jobs | `GET /jobs/{id}` | Poll for result instead of blocking |
| 2. Self-refining content generator | Async jobs | `GET /jobs/{id}` | Same as above |
| 3. Event-aware profile agent | Event hook + push | `GET /notifications/{user_id}/stream` (SSE) | Add polling/SSE listener for profile changes |
| 4. Session orchestrator | Compound endpoint | `POST /learning/next-action` | Replace 4-5 calls with 1 |
| 5. Skill gap assessment | Multi-step session | `POST /skill-gap/start-assessment`, `POST /skill-gap/submit-answers` | Quiz UI within skill gap flow |
| 6. Source quality judgment | None (internal) | No change | No change |
| 7. Adaptive quiz probing | Multi-step session | `POST /quiz/start-adaptive`, `POST /quiz/submit-answer` | Dynamic quiz UI |

### Endpoints that stay the same (but take longer)
- `POST /events/log` — same interface, but now triggers background processing
- `GET /profile/{user_id}` — same interface, but profile may have been updated in background

### Endpoints that become async
- `POST /schedule-learning-path` → returns job_id
- `POST /tailor-knowledge-content` → returns job_id
- `POST /iterative-refine-path` → removed (refinement is now internal to the scheduler)

### Endpoints that split into multi-step
- `POST /identify-skill-gap-with-info` → split into `/skill-gap/start-assessment` + `/skill-gap/submit-answers`

### New infrastructure endpoints
- `GET /jobs/{id}` — poll job status and progress
- `GET /jobs/{id}/stream` — SSE stream for real-time progress (optional)
- `GET /notifications/{user_id}/stream` — SSE stream for push notifications (profile updates, etc.)

---

## Streamlit-Specific Considerations

Streamlit is a challenge for these patterns because it's not designed for:
- Long-lived WebSocket connections
- Background event listeners
- Partial page updates without full rerun

**Pragmatic workarounds:**

1. **For async jobs:** Use `st.status()` with polling inside a `while` loop. Streamlit 1.29+ supports `st.status` containers that update in place.

2. **For push notifications:** Use `st.fragment` (experimental) for a small component that polls `/profile/{user_id}` every 10-15 seconds without triggering a full page rerun.

3. **For multi-step sessions:** Use `st.session_state` to track the assessment session_id and render quiz questions as Streamlit form elements. Each form submission calls `/submit-answers` and rerenders.

4. **If Streamlit becomes the bottleneck:** Consider migrating to a React/Next.js frontend, which natively supports SSE (`EventSource`), WebSockets, and partial updates. The backend API patterns described above are framework-agnostic.
