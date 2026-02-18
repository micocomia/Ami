# Making the System More Agentic

## The Current Gap

The system today is a **pipeline**, not an **agent system**. Every agent is a single LLM call wrapped in Pydantic validation — it receives input, produces output, and has no ability to decide what to do next. All orchestration logic lives in Python functions (`create_learning_content_with_llm`, `identify_skill_gap_with_llm`, etc.) that hardcode the execution order.

The key limitation: **no agent can decide to call another agent, use a tool, or loop on its own judgment**. The `BaseAgent` class accepts a `tools` parameter, and `create_simulate_feedback_tool` already exists as a LangChain tool in `tools/learner_simulation_tool.py` — but it's never wired into any agent. The infrastructure for tool-use is there; it's just not connected.

Below are concrete proposals for making the system more agentic, ordered from most impactful to most speculative.

---

## 1. Self-Refining Learning Path Scheduler

### Current behavior
The learning path scheduler creates a path in one shot (`schedule_session`). Refinement only happens when explicitly triggered by the frontend via `/iterative-refine-path`, which runs a hardcoded `for` loop:

```python
for i in range(max_iterations):
    feedback = simulate_path_feedback_with_llm(llm, profile, current_path)
    current_path = refine_learning_path_with_llm(llm, current_path, feedback)
```

The agent has no say in whether to refine or when to stop.

### Agentic version
Give the `LearningPathScheduler` the `simulate_learner_feedback` tool (which already exists but is unused). The scheduler would:

1. Generate an initial path
2. **Decide on its own** whether to call the simulation tool to get feedback
3. Read the feedback and **decide** whether refinement is needed or the path is good enough
4. Refine and re-evaluate until **it** judges the path is satisfactory

**Implementation sketch:**
```python
feedback_tool = create_simulate_feedback_tool(llm)

scheduler = LearningPathScheduler(
    model=llm,
    tools=[feedback_tool],  # Agent can now call this tool
)
```

The system prompt would be updated to say: "After generating a path, you SHOULD use the `simulate_learner_feedback` tool to evaluate it. If the feedback identifies significant issues in progression or personalization, refine the path and re-evaluate. Stop when the feedback is satisfactory or after 3 tool calls."

**What changes:**
- The agent controls the loop, not Python code
- The agent can choose to skip refinement for simple goals
- The agent can stop early if the first path is already strong
- `langgraph`'s `create_agent` already supports tool-calling loops natively

**Key risk:** LLM may over-refine or get stuck in a loop. Mitigate with a max tool-call limit in the agent config (`interrupt_after` or a counter in the system prompt).

---

## 2. Self-Refining Content Generator

### Current behavior
Content generation is a fixed 4-step pipeline: explore knowledge points -> draft each point -> integrate -> generate quiz. No step evaluates the quality of its output.

### Agentic version
Give the `LearningContentCreator` or a new **Content Orchestrator** agent tools for:

- `explore_knowledge_points` — identify what to teach
- `draft_knowledge_point` — draft a single point with RAG
- `integrate_document` — synthesize drafts
- `generate_quiz` — create assessment
- `simulate_content_feedback` — evaluate the result

The orchestrator would:
1. Explore knowledge points
2. Draft them (can decide to parallelize or do sequentially)
3. Integrate into a document
4. **Call the content feedback tool** to evaluate
5. If feedback says "content doesn't match learner's preferred style" or "missing practical examples," the agent **re-drafts specific sections** rather than regenerating everything
6. Re-evaluate until satisfied

**What this enables that the pipeline can't do:**
- Selective re-drafting (only the weak section, not the whole document)
- The agent can decide "this learner needs more examples" and call the drafter again for a specific knowledge point
- The agent can skip the quiz for a session that's purely conceptual

---

## 3. Event-Aware Profile Agent

### Current behavior
Profile updates are triggered externally: the frontend calls `POST /profile/auto-update`, which dumps all accumulated events into the profiler. The profiler has no awareness of the event store and no ability to decide *when* or *whether* an update is warranted.

### Agentic version
Give the `AdaptiveLearnerProfiler` a `check_event_log` tool:

```python
@tool("check_event_log")
def check_event_log(user_id: str) -> Dict[str, Any]:
    """Check the learner's recent event log to determine if a profile update is needed.

    Returns event summary: count, types, timestamps, and time since last profile update.
    """
    events = store.get_events(user_id)
    recent = events[-20:]  # Last 20 events
    return {
        "total_events": len(events),
        "recent_events": recent,
        "event_types": list(set(e["event_type"] for e in recent)),
        "latest_timestamp": recent[-1]["ts"] if recent else None,
    }
```

The profiler would be invoked periodically (cron, or on each login) and would:
1. Call `check_event_log` to see what's happened
2. **Decide** whether the events warrant a profile update (e.g., 3 quiz failures in a row = yes, 2 page views = no)
3. If yes, pull the full event data and update the profile
4. If no, return the current profile unchanged

**What this enables:**
- The agent applies judgment about update frequency instead of the frontend guessing
- Saves LLM calls when nothing meaningful has happened
- The agent can reason about *patterns* (e.g., "login frequency dropped — add motivational trigger") rather than just processing raw events

**Extension — profile update with tool access to skill gaps:**
Give the profiler a `recheck_skill_gaps` tool so it can re-run the skill gap identifier when it suspects the learner's current level assessment is outdated (e.g., after a string of perfect quiz scores).

---

## 4. Autonomous Learning Session Orchestrator

### Current behavior
The frontend drives the learning loop: it calls `/schedule-learning-path`, then for each session calls `/tailor-knowledge-content`, then logs events, then calls `/profile/auto-update`, then calls `/reschedule-learning-path`. Each step is a separate API call with no awareness of the overall goal.

### Agentic version
Create a top-level **Session Orchestrator** agent with tools for every sub-agent:

```python
tools = [
    check_event_log_tool,
    update_profile_tool,
    schedule_path_tool,
    reschedule_path_tool,
    generate_content_tool,
    simulate_feedback_tool,
    check_quiz_results_tool,
]

orchestrator = SessionOrchestrator(model=llm, tools=tools)
```

Invoked with: "The learner just completed Session 3 with quiz scores [80%, 60%, 90%]. Decide what to do next."

The orchestrator could:
1. Call `check_quiz_results_tool` to analyze performance
2. Decide the 60% quiz score indicates a gap in one skill
3. Call `update_profile_tool` to lower that skill's proficiency
4. Call `reschedule_path_tool` to insert a remedial session
5. Call `generate_content_tool` for the new session
6. Call `simulate_feedback_tool` to validate the new content
7. Return the updated path + content to the frontend

**What this enables:**
- Single API call replaces 4-5 separate frontend calls
- The agent can make decisions the frontend currently can't (e.g., "insert a remedial session" vs. "move on")
- The orchestrator sees the full picture and can reason about trade-offs

**Key risk:** Long execution time (multiple LLM calls chained). Mitigate with async execution + job status polling, and use a fast model for tool dispatch.

---

## 5. Skill Gap Identifier with Assessment Strategy Selection

### Current behavior
The skill gap identifier infers the learner's current level from their resume/background in a single pass. For every skill, it uses the same approach: read the resume, guess the level, assign a confidence. If the information is ambiguous, it assigns `low` confidence and moves on. There is no way to gather additional evidence.

### Agentic version
Give the `SkillGapIdentifier` tools to autonomously choose its assessment strategy per skill:

```python
@tool("analyze_resume_for_skill")
def analyze_resume_for_skill(skill_name: str, learner_information: str) -> Dict[str, Any]:
    """Analyze the learner's resume/background to infer their level for a specific skill.

    Returns an assessment with inferred level and confidence.
    """
    # Focused analysis of resume for one skill
    return {"skill": skill_name, "inferred_level": "multistructural", "confidence": "medium",
            "evidence": "Resume mentions 2 projects using this skill but no integration across them"}

@tool("administer_diagnostic_quiz")
def administer_diagnostic_quiz(skill_name: str, suspected_level: str) -> Dict[str, Any]:
    """Generate and administer a short diagnostic quiz (2-3 questions) to determine
    the learner's actual SOLO level for a specific skill.

    Generates questions at the suspected level and one level above to pinpoint
    the boundary of the learner's understanding.
    """
    # 1. Generate 2-3 questions targeting the suspected SOLO level boundary
    # 2. Present to learner (via interrupt/pause or async callback)
    # 3. Evaluate responses
    # 4. Return assessed level with high confidence
    return {"skill": skill_name, "assessed_level": "relational", "confidence": "high",
            "quiz_summary": "Correctly explained concept relationships, struggled with transfer"}

@tool("request_clarification")
def request_clarification(question: str, skill_name: str) -> str:
    """Ask the learner a single clarifying question about their experience with a skill."""
    ...
```

The agent would then decide **per skill** which assessment strategy to use:

1. **Resume alone is sufficient** (high confidence from background info):
   - Learner has a degree in the exact field -> `analyze_resume_for_skill` is enough
   - Example: A statistics PhD listing "Advanced Bayesian Inference" -> agent assigns `relational` with `high` confidence, no quiz needed

2. **Resume is ambiguous, quiz needed** (low confidence from background info):
   - Learner mentions "some experience with machine learning" -> agent calls `administer_diagnostic_quiz("Machine Learning", "multistructural")`
   - The quiz tests whether the learner can connect ML concepts (relational) or only list them (multistructural)
   - Example: A bootcamp graduate listing "Python" — could be unistructural (knows syntax) or multistructural (knows multiple libraries). A 2-question diagnostic resolves this

3. **No information at all, quick clarification first**:
   - Skill not mentioned in resume -> agent calls `request_clarification("Have you worked with Docker in any capacity?", "Docker")`
   - Based on the answer, decides whether a quiz is needed or the answer is sufficient

**Decision flow the agent would follow:**
```
For each required skill:
  1. analyze_resume_for_skill(skill)
  2. If confidence == "high" → done, use inferred level
  3. If confidence == "medium" → request_clarification to disambiguate
  4. If confidence == "low" or skill not in resume → administer_diagnostic_quiz
```

The critical insight is that **the agent decides the strategy, not a hardcoded rule**. It might determine that for a learner with a detailed GitHub portfolio, no quizzes are needed for any skill. For a learner with a vague 1-paragraph bio, it might quiz on 4 out of 6 skills. This is fundamentally different from a system that always quizzes or never quizzes.

**SOLO-specific benefit:** The diagnostic quiz would be designed around SOLO level boundaries. Testing multistructural vs. relational is the hardest distinction — a quiz asking "explain how X and Y relate" (relational) vs. "list the features of X and Y" (multistructural) directly maps to SOLO and is much more precise than a generic "beginner/intermediate/advanced" self-assessment.

**What this enables:**
- Higher confidence assessments without burdening every learner with quizzes
- The agent applies judgment about when evidence is sufficient
- SOLO levels are assessed through appropriate methods (resume analysis for clear cases, targeted quizzes for ambiguous ones)
- Fewer wasted sessions teaching skills the learner already has

**Implementation consideration:** The `administer_diagnostic_quiz` tool requires an async/resumable agent pattern — the agent pauses while the learner answers, then resumes. LangGraph's `interrupt_before` + checkpointing supports this natively. For a simpler first version, the quiz could be asynchronous: the agent flags which skills need quizzes, the frontend collects answers, and the agent is re-invoked with the results.

---

## 6. Knowledge Drafter with Source Quality Judgment

### Current behavior
The `SearchEnhancedKnowledgeDrafter` calls `SearchRagManager.invoke(query)` once, gets whatever comes back from DuckDuckGo + Chroma, and uses it. No judgment about source quality.

### Agentic version
Give the drafter tools for:
- `web_search(query)` — search the web
- `retrieve_from_knowledge_base(query)` — search the vector store
- `evaluate_source(content, criteria)` — judge relevance and quality

The drafter would:
1. Search for the knowledge point
2. **Evaluate** whether the retrieved sources are high enough quality
3. If not, **reformulate the query** and search again
4. If the knowledge base has good content, prefer it over web results
5. Draft using only the sources it judged adequate

**What this enables:**
- Better content quality through source curation
- The agent learns to reformulate bad queries instead of using bad sources
- Reduced hallucination from irrelevant search results

---

## 7. Quiz Generator with Adaptive Difficulty Probing

### Current behavior
The quiz generator creates a fixed set of questions in one pass based on the learner's profile. The difficulty is inferred from the profile, not tested.

### Agentic version
Give the quiz generator a `check_learner_response` tool (for real-time quiz delivery):

1. Generate a medium-difficulty question
2. Present it to the learner
3. If they get it right easily, **generate a harder one** (moving up a SOLO level)
4. If they struggle, **generate an easier one** (moving down)
5. Stop when it has pinpointed the learner's actual level

This turns the quiz from a static assessment into a **computerized adaptive test** (CAT), driven by the agent's judgment rather than a fixed algorithm.

**Implementation consideration:** Requires real-time interaction, which means the agent needs to maintain state across multiple request-response cycles. LangGraph checkpointing or a WebSocket-based session would support this.

---

## Implementation Priority

| Proposal | Impact | Effort | Dependencies |
|----------|--------|--------|-------------|
| 1. Self-refining path scheduler | High | Low | Tool already exists, just wire it in |
| 3. Event-aware profile agent | High | Low | Simple tool wrapping `store.get_events` |
| 2. Self-refining content generator | High | Medium | Need to wrap sub-agents as tools |
| 5. Skill gap assessment strategy | High | Medium | Resume tool is easy; diagnostic quiz needs async pattern |
| 6. Source quality judgment | Medium | Medium | Need source evaluation tool |
| 4. Session orchestrator | Very High | High | Depends on 1, 2, 3 being done first |
| 7. Adaptive quiz probing | High | High | Needs real-time interaction pattern |

### Recommended starting point
**Proposals 1 and 3** — they're the lowest-effort, highest-impact changes. The feedback simulation tool already exists and just needs to be passed to the scheduler's `tools` parameter. The event log tool is a thin wrapper around `store.get_events`. Both demonstrate genuine agentic behavior (agent decides whether and when to act) with minimal architectural changes.

**Proposal 5 (skill gap assessment strategy)** is the natural next step, especially if combined with the SOLO taxonomy. A simplified first version — where the agent decides "resume is sufficient" vs. "flag for quiz" without the async quiz delivery — can be done at medium effort and immediately improves assessment quality.

---

## Architectural Notes for Tool-Use Agents

### How `BaseAgent` already supports tools
The `__init__` accepts `tools: Optional[list[Any]]` and passes them to `create_agent()`. LangChain's `create_agent` (backed by LangGraph) handles the tool-calling loop automatically — the LLM decides when to call a tool, processes the result, and decides whether to call another tool or return a final answer.

The current limitation is that **no agent actually passes tools**. Every agent is instantiated with `tools=None` (or implicitly `None`), making them single-shot LLM calls. Enabling tool use is literally a matter of passing tools to the constructor.

### Output validation with tools
When an agent uses tools, it may take multiple turns before producing a final answer. The current `invoke()` method calls `preprocess_response()` on the final output, which extracts JSON. This should still work as long as the final message is the structured output. However, tool-calling agents may need a modified validation flow that distinguishes intermediate tool results from the final answer.

### Cost and latency considerations
Each tool call is an additional LLM round-trip. A self-refining scheduler with 2 feedback cycles = 5 LLM calls (initial + 2 simulations + 2 refinements) instead of 1. Use a faster/cheaper model for tool execution (the feedback tool already uses `gpt-4o-mini`) and set clear max iteration limits.

### LangGraph features available but unused
The codebase imports `langgraph` types but doesn't use LangGraph's key features:
- **Checkpointing**: Save and resume agent state (needed for proposals 5 and 7)
- **Interrupts**: Pause the agent to collect user input (needed for proposal 5)
- **State graphs**: Define complex agent workflows as graphs with conditional edges (needed for proposal 4)

These are all available via the existing `langgraph` (1.0.7) dependency.
