# GenMentor Backend System Summary

Preparation doc for AI engineer role interviews. Covers the tech stack, multi-agent architecture, agent interaction patterns, and productionization considerations.

---

## 1. Tech Stack

### Core Framework
- **FastAPI** (0.128.0) — async web framework serving all API endpoints
- **Uvicorn** (0.40.0) — ASGI server
- **Pydantic** (2.12.5) — data validation for every agent input/output and API schema

### LLM Orchestration
- **LangChain** (1.0.0) — core abstraction layer for LLM calls
  - `langchain-core` (1.2.8) — base `BaseChatModel`, `Document`, `Embeddings` abstractions
  - `langchain-openai` (1.1.7) — OpenAI model integration
  - `langchain.agents.create_agent` — builds agents compatible with LangGraph
  - `langgraph` (1.0.7) — graph-based agent orchestration (available but not heavily used; the system uses functional composition instead)
- **OpenAI** (2.16.0) — default LLM provider (GPT-4o)

### RAG (Retrieval-Augmented Generation)
- **Chroma** (1.4.1) — vector database with local persistence (`data/vectorstore/`)
- **sentence-transformers** (5.2.2) via `langchain-huggingface` — embeddings (`all-mpnet-base-v2`)
- **duckduckgo_search** (8.1.1) — free web search (no API key required)
- **Docling** (2.71.0) — document loading and parsing

### Document Processing
- **pdfplumber**, **PyPDF2**, **pypdf**, **pdfminer.six** — PDF extraction
- **python-docx** — DOCX parsing
- **python-pptx** — PowerPoint parsing
- **beautifulsoup4** — HTML parsing

### Configuration
- **Hydra** (1.3.2) + **OmegaConf** (2.3.0) — YAML-based config management (`config/default.yaml`)

### Auth
- **PyJWT** (2.11.0) — JWT tokens (24h expiry)
- **bcrypt** (5.0.0) — password hashing

### Storage
- **JSON file-based** persistence (thread-safe with `threading.Lock`)
  - `data/profiles.json` — learner profiles keyed by `user_id:goal_id`
  - `data/events.json` — behavior events per user (capped at 200)
  - `data/users.json` — user credentials (bcrypt hashes)
  - `data/user_states.json` — generic UI state blobs

---

## 2. Architecture Overview

```
Client (Streamlit Frontend)
  │
  ▼
FastAPI Server (main.py)
  │
  ├── Auth Layer (JWT + bcrypt)
  │
  ├── API Endpoints ──► Convenience Functions (e.g., identify_skill_gap_with_llm)
  │                          │
  │                          ▼
  │                     Agent Instances (BaseAgent subclasses)
  │                          │
  │                          ├── LLMFactory.create() ──► LangChain BaseChatModel
  │                          ├── Pydantic Payload Validation (input)
  │                          ├── LLM Invocation (system prompt + task prompt)
  │                          ├── JSON Extraction + Think-tag Removal
  │                          └── Pydantic Schema Validation (output)
  │
  ├── SearchRagManager (singleton, created at startup)
  │     ├── SearchRunner (DuckDuckGo) ──► web results
  │     ├── WebDocumentLoader ──► Document objects
  │     ├── TextSplitter (RecursiveCharacter, 1000 chars)
  │     ├── Chroma VectorStore ──► add + similarity_search
  │     └── format_docs() ──► context string for LLM
  │
  └── JSON File Store (profiles, events, users, ui state)
```

---

## 3. BaseAgent Pattern

Every agent in the system extends `BaseAgent` (`base/base_agent.py`). This is the key abstraction to understand:

```python
class BaseAgent:
    def __init__(self, model, system_prompt, tools=None, jsonalize_output=True):
        self._agent = create_agent(model=model, tools=tools, system_prompt=system_prompt)

    def invoke(self, input_dict, task_prompt):
        # 1. Format task_prompt with input_dict variables
        # 2. Call LLM via self._agent.invoke()
        # 3. Extract text from response
        # 4. Remove <think> tags (for reasoning models)
        # 5. Parse as JSON if jsonalize_output=True
        return processed_output
```

**Key design decisions:**
- System prompt is set once at agent construction (defines the agent's role)
- Task prompt is passed per invocation (defines what to do this time)
- Every agent validates input with a Pydantic `Payload` model and output with a Pydantic `Schema` model
- Agents are stateless — no memory between invocations. Context is passed explicitly in the task prompt
- Temperature is always 0 (deterministic outputs)

---

## 4. Agents and Their Interactions

### Module 1: Skill Gap Identification

#### Learning Goal Refiner
- **Purpose**: Refines a vague learning goal into a specific, actionable one
- **Input**: raw learning goal + learner information
- **Output**: `RefinedLearningGoal`
- **Interactions**: Standalone. Called optionally before the skill gap pipeline

#### Skill Requirement Mapper
- **Purpose**: Maps a learning goal to a list of 1-10 required skills with proficiency levels
- **Input**: `learning_goal`
- **Output**: `SkillRequirements` (list of `{name, required_level}`)
- **Interactions**: Called by `SkillGapIdentifier` when no pre-computed requirements exist

#### Skill Gap Identifier
- **Purpose**: Compares learner's background against required skills to find gaps
- **Input**: `learning_goal` + `learner_information` + `skill_requirements`
- **Output**: `SkillGaps` (list of `{name, is_gap, required_level, current_level, reason, confidence}`)
- **Interactions**:
  - **Calls** `SkillRequirementMapper` internally if `skill_requirements` not provided
  - **Output consumed by** `AdaptiveLearnerProfiler` for profile initialization

**Interaction pattern** (`identify_skill_gap_with_llm`):
```
identify_skill_gap_with_llm(llm, goal, info, requirements=None)
  │
  ├── if requirements is None:
  │     SkillRequirementMapper.map_goal_to_skill(goal)
  │     └── returns: skill_requirements dict
  │
  └── SkillGapIdentifier.identify_skill_gap(goal, info, skill_requirements)
        └── returns: (skill_gaps, skill_requirements) tuple
```

---

### Module 2: Adaptive Learner Modeling

#### Adaptive Learner Profiler
- **Purpose**: Creates and updates comprehensive learner profiles (cognitive status, FSLSM learning style, behavioral patterns)
- **Input (init)**: `learning_goal` + `learner_information` + `skill_gaps`
- **Input (update)**: `learner_profile` + `learner_interactions` + `learner_information` + `session_information`
- **Output**: `LearnerProfile`
- **Interactions**:
  - **Consumes output from** `SkillGapIdentifier` — skill gaps become the cognitive status baseline
  - **Output consumed by** every agent in the Personalized Resource Delivery module — the profile drives all personalization
  - **Consumes events** from the Event Store — behavior logs feed profile updates

**Interaction pattern** (profile lifecycle):
```
1. INITIALIZATION (one-time):
   SkillGapIdentifier output (skill_gaps)
     └──► AdaptiveLearnerProfiler.initialize_profile()
           └── returns: LearnerProfile

2. UPDATE (continuous):
   Event Store (learner_interactions) + Session metadata
     └──► AdaptiveLearnerProfiler.update_profile()
           └── returns: updated LearnerProfile
```

---

### Module 3: Personalized Resource Delivery

This module contains 7 agents that form two pipelines: path scheduling and content generation.

#### Learning Path Scheduler
- **Purpose**: Creates, refines, and reschedules personalized learning paths (1-10 sessions)
- **Input**: `learner_profile` (from Adaptive Learner Profiler)
- **Output**: `LearningPath` (list of `SessionItem` with `desired_outcome_when_completed`)
- **Interactions**:
  - **Consumes** `LearnerProfile` from `AdaptiveLearnerProfiler`
  - **Consumes** `LearnerFeedback` from `LearnerFeedbackSimulator` (for reflexion/refinement)
  - **Output consumed by** Knowledge Explorer, Knowledge Drafter, Content Creator, Document Integrator (all need the path for context)
- **Three modes**:
  - Task A (`schedule_session`): New path from profile
  - Task B (`reflexion`): Refine unlearned sessions based on feedback
  - Task C (`reschedule`): Update path preserving learned sessions

#### Learner Feedback Simulator
- **Purpose**: Role-plays as the learner to generate realistic feedback on paths or content
- **Input**: `learner_profile` + `learning_path` (or `learning_content`)
- **Output**: `LearnerFeedback` (feedback + suggestions on progression/engagement/personalization)
- **Interactions**:
  - **Consumes** `LearnerProfile` from `AdaptiveLearnerProfiler`
  - **Consumes** `LearningPath` from `LearningPathScheduler`
  - **Output consumed by** `LearningPathScheduler.reflexion()` for path refinement

**Iterative refinement loop** (`/iterative-refine-path` endpoint):
```
for i in range(max_iterations):  # capped at 5
  feedback = LearnerFeedbackSimulator.feedback_path(profile, current_path)
  current_path = LearningPathScheduler.reflexion(current_path, feedback)
```

#### Goal-Oriented Knowledge Explorer
- **Purpose**: Identifies key knowledge points for a specific session
- **Input**: `learner_profile` + `learning_path` + `learning_session`
- **Output**: `KnowledgePoints` (list of `{name, type}` where type is foundational/practical/strategic)
- **Interactions**:
  - **Consumes** `LearnerProfile` + `LearningPath`
  - **Output consumed by** `SearchEnhancedKnowledgeDrafter` and `LearningDocumentIntegrator`

#### Search-Enhanced Knowledge Drafter
- **Purpose**: Drafts markdown content for individual knowledge points, enriched with web search via RAG
- **Input**: `learner_profile` + `learning_path` + `learning_session` + `knowledge_points` + `knowledge_point` + `external_resources`
- **Output**: `KnowledgeDraft` (title + markdown content)
- **Interactions**:
  - **Consumes** `KnowledgePoints` from `GoalOrientedKnowledgeExplorer`
  - **Calls** `SearchRagManager.invoke(query)` internally for RAG enrichment
  - **Output consumed by** `LearningDocumentIntegrator`
  - **Supports parallel execution** via `ThreadPoolExecutor` — multiple knowledge points drafted simultaneously

#### Learning Document Integrator
- **Purpose**: Synthesizes multiple knowledge drafts into a single cohesive learning document
- **Input**: `learner_profile` + `learning_path` + `learning_session` + `knowledge_points` + `knowledge_drafts`
- **Output**: `DocumentStructure` (title, overview, content, summary) or raw markdown
- **Interactions**:
  - **Consumes** `KnowledgePoints` from `GoalOrientedKnowledgeExplorer`
  - **Consumes** `KnowledgeDraft` list from `SearchEnhancedKnowledgeDrafter`
  - **Output consumed by** `DocumentQuizGenerator`

#### Document Quiz Generator
- **Purpose**: Creates quiz questions from a learning document, difficulty-tailored to the learner
- **Input**: `learner_profile` + `learning_document` + question counts per type
- **Output**: `DocumentQuiz` (single-choice, multiple-choice, true/false, short-answer questions)
- **Interactions**:
  - **Consumes** `LearnerProfile` from `AdaptiveLearnerProfiler`
  - **Consumes** document from `LearningDocumentIntegrator`
  - **Output consumed by** the frontend for learner assessment; quiz results feed back into the Event Store

#### Learning Content Creator
- **Purpose**: Alternative content creation agent that can generate outlines, draft sections, or produce complete documents
- **Input**: `learner_profile` + `learning_path` + `learning_session` + `external_resources`
- **Output**: `ContentOutline`, `KnowledgeDraft`, or `LearningContent`
- **Interactions**: Can be used as a standalone alternative to the Knowledge Explorer -> Drafter -> Integrator pipeline

**Full content generation pipeline** (`create_learning_content_with_llm`, "genmentor" method):
```
create_learning_content_with_llm(llm, profile, path, session)
  │
  ├── 1. GoalOrientedKnowledgeExplorer.explore()
  │       └── returns: knowledge_points [{name, type}, ...]
  │
  ├── 2. SearchEnhancedKnowledgeDrafter.draft() × N  [PARALLEL via ThreadPoolExecutor]
  │       ├── For each knowledge_point:
  │       │     SearchRagManager.invoke(query)   ← web search + vectorstore
  │       │       ├── SearchRunner.invoke()       ← DuckDuckGo search
  │       │       ├── WebDocumentLoader.invoke()  ← fetch URLs
  │       │       ├── add_documents()             ← store in Chroma
  │       │       └── retrieve()                  ← similarity search
  │       └── returns: knowledge_drafts [{title, content}, ...]
  │
  ├── 3. LearningDocumentIntegrator.integrate()
  │       └── returns: DocumentStructure or markdown string
  │
  └── 4. DocumentQuizGenerator.generate()  [optional]
          └── returns: DocumentQuiz
```

---

### Module 4: AI Chatbot Tutor

#### AI Tutor Chatbot
- **Purpose**: Interactive conversational tutor with RAG-enhanced responses
- **Input**: message history + `learner_profile` (optional)
- **Output**: text response
- **Interactions**:
  - **Consumes** `LearnerProfile` for personalized responses
  - **Calls** `SearchRagManager` for context-aware answers
  - Stateless per request — message history passed in each call

---

### Module 5: Learner Simulation (Testing/Evaluation)

#### Ground Truth Profile Creator
- **Purpose**: Generates realistic learner personas for system testing
- **Input**: `learning_goal` + `learner_information`
- **Output**: detailed ground-truth learner profile
- **Interactions**: Output used by `LearnerInteractionSimulator` and `LearnerFeedbackSimulator` for richer simulation

#### Learner Interaction Simulator
- **Purpose**: Simulates realistic learner behavior logs for testing the profile update pipeline
- **Input**: `ground_truth_profile` + `session_number`
- **Output**: behavior logs (interaction patterns, performance, engagement)
- **Interactions**: Output feeds into the Event Store, which then triggers `AdaptiveLearnerProfiler.update_profile()`

---

## 5. Multi-Agent Interaction Patterns

### Pattern 1: Sequential Pipeline (Most Common)
Agents execute in a fixed order. Each agent's output is the next agent's input.

```
SkillRequirementMapper → SkillGapIdentifier → AdaptiveLearnerProfiler
```

**How it works in code:**
- Each step is a separate function call in a convenience wrapper (e.g., `identify_skill_gap_with_llm`)
- Data is passed as plain Python dicts between steps
- No shared memory or message bus — pure function composition
- Each agent is instantiated fresh per call (stateless)

### Pattern 2: Fan-Out / Parallel Execution
Multiple instances of the same agent run simultaneously on different inputs.

```
KnowledgeExplorer → [KnowledgeDrafter × N in parallel] → DocumentIntegrator
```

**How it works in code:**
```python
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    results = list(executor.map(draft_one, knowledge_points))
```
- Each drafter independently calls SearchRagManager for its knowledge point
- Results collected and passed to the integrator
- Configurable via `allow_parallel` flag and `max_workers` setting

### Pattern 3: Feedback Loop (Reflexion)
Two agents iterate: one generates, the other evaluates, and the generator refines.

```
LearningPathScheduler ←→ LearnerFeedbackSimulator  (up to 5 iterations)
```

**How it works in code:**
```python
for i in range(max_iterations):
    feedback = simulate_path_feedback_with_llm(llm, profile, current_path)
    current_path = refine_learning_path_with_llm(llm, current_path, feedback)
```
- The scheduler has separate methods for generation (`schedule_session`) vs. refinement (`reflexion`)
- The feedback simulator role-plays as the learner to produce realistic critiques
- Iteration count is capped (max 5) to prevent infinite loops

### Pattern 4: Conditional Delegation
An agent calls another agent only when needed.

```
SkillGapIdentifier ──(if no requirements)──► SkillRequirementMapper
```

**How it works in code:**
```python
if not skill_requirements:
    mapper = SkillRequirementMapper(llm)
    effective_requirements = mapper.map_goal_to_skill({"learning_goal": learning_goal})
```

### Pattern 5: Event-Driven Update
External events accumulate and periodically trigger an agent.

```
Frontend → POST /events/log → Event Store → POST /profile/auto-update → AdaptiveLearnerProfiler
```

- Events (quiz results, session completions, engagement signals) accumulate in the store
- When `/profile/auto-update` is called, all pending events are batched and passed to the profiler
- The profiler decides how to update cognitive status, FSLSM dimensions, and behavioral patterns

---

## 6. Data Flow: End-to-End User Journey

```
1. USER ONBOARDING
   User uploads resume + sets learning goal
     │
     ▼
   POST /refine-learning-goal
     └── LearningGoalRefiner → refined goal
     │
     ▼
   POST /identify-skill-gap-with-info
     ├── SkillRequirementMapper → required skills
     └── SkillGapIdentifier → skill gaps with confidence
     │
     ▼
   POST /profile/auto-update (mode: initialize)
     └── AdaptiveLearnerProfiler.initialize_profile()
         └── LearnerProfile stored in profiles.json

2. LEARNING PATH CREATION
   POST /schedule-learning-path
     └── LearningPathScheduler.schedule_session(profile)
         └── LearningPath (5 sessions with desired outcomes)
     │
     ▼
   POST /iterative-refine-path (optional)
     ├── LearnerFeedbackSimulator.feedback_path() × N
     └── LearningPathScheduler.reflexion() × N
         └── Refined LearningPath

3. CONTENT GENERATION (per session)
   POST /tailor-knowledge-content
     ├── GoalOrientedKnowledgeExplorer.explore()
     ├── SearchEnhancedKnowledgeDrafter.draft() × N  [parallel]
     │     └── SearchRagManager.invoke() per point
     ├── LearningDocumentIntegrator.integrate()
     └── DocumentQuizGenerator.generate()
         └── {document, quizzes}

4. LEARNING LOOP
   User studies content, takes quizzes
     │
     ▼
   POST /events/log (quiz_result, session_complete, engagement)
     └── Events stored in events.json
     │
     ▼
   POST /profile/auto-update (mode: update)
     └── AdaptiveLearnerProfiler.update_profile(profile, events, session_info)
         └── Updated profile (skills may move to mastered)
     │
     ▼
   POST /reschedule-learning-path
     └── LearningPathScheduler.reschedule(updated_profile, current_path)
         └── Updated path preserving learned sessions
     │
     ▼
   Repeat step 3 for next session
```

---

## 7. Productionization Considerations

### What the current system does well
- **Clean agent abstraction**: BaseAgent + Pydantic validation makes agents composable and testable
- **Parallel execution**: ThreadPoolExecutor for knowledge drafting is a pragmatic choice
- **Stateless agents**: No shared mutable state between agents — easy to scale horizontally
- **Config-driven**: Hydra/OmegaConf makes swapping models/providers a config change

### What would need to change for production

#### Storage
- **Current**: JSON files with thread locks. Single-process only, no durability guarantees
- **Production**: PostgreSQL or MongoDB for profiles/events. Redis for session state and caching
- **Why**: JSON files don't survive crashes mid-write, can't handle concurrent processes, and don't scale

#### Authentication
- **Current**: JWT secret hardcoded as `"dev-secret-change-in-production"`. No refresh tokens
- **Production**: Environment-injected secrets, refresh token rotation, rate limiting on auth endpoints

#### Observability
- **Current**: Basic Python logging
- **Production**: Structured logging (JSON), distributed tracing (OpenTelemetry) across agent calls, LLM call latency/cost tracking (LangSmith or custom), error alerting

#### LLM Reliability
- **Current**: No retry logic, no fallback models, no token budget tracking
- **Production**:
  - Retry with exponential backoff on transient failures
  - Fallback model chain (GPT-4o → GPT-4o-mini → local model)
  - Token usage tracking and budget enforcement per user
  - Response caching for identical inputs (especially skill mapping, which is deterministic)
  - Timeout enforcement per agent call

#### Async / Queue-Based Execution
- **Current**: Synchronous agent calls within async FastAPI endpoints (blocking the event loop)
- **Production**:
  - Move agent pipelines to background workers (Celery + Redis, or cloud task queues)
  - Return job IDs immediately, poll for results
  - Especially important for `create_learning_content_with_llm` which chains 4+ LLM calls

#### RAG
- **Current**: Chroma with local persistence, DuckDuckGo search
- **Production**:
  - Managed vector database (Pinecone, Weaviate, or pgvector)
  - Curated knowledge base instead of/alongside web search
  - Document deduplication in the vector store
  - Embedding versioning (re-embed when model changes)

#### Agent Evaluation
- **Current**: Learner simulation module for testing, but no systematic evaluation framework
- **Production**:
  - Automated evaluation suites that measure agent output quality
  - A/B testing different prompts or model versions
  - Human-in-the-loop review for edge cases
  - Regression tests when prompts change

#### Multi-Tenancy and Scaling
- **Current**: Single-process, single-machine
- **Production**:
  - Containerized deployment (Docker already partially set up)
  - Horizontal scaling behind a load balancer
  - Per-user rate limiting on LLM calls
  - Shared SearchRagManager instance needs to become per-tenant or use a managed service

---

## 8. Interview Talking Points

### "How does the multi-agent system work?"
> The system uses functional composition rather than an agent framework like CrewAI or AutoGen. Each agent is a LangChain-based wrapper around a single LLM call with a specialized system prompt. Agents are stateless — they receive all context in the task prompt and return validated JSON. Agent orchestration happens in convenience functions that chain outputs to inputs, with Pydantic enforcing contracts at every boundary. This is simpler than graph-based orchestration but trades off flexibility for predictability.

### "How do agents communicate?"
> Through plain Python dicts. There's no message bus or shared memory. One agent's validated output becomes the next agent's input via function arguments. For parallel execution, we use ThreadPoolExecutor to fan out the knowledge drafter across multiple knowledge points, then collect results for the integrator. For feedback loops, the scheduler and feedback simulator alternate in a for-loop capped at 5 iterations.

### "Why not use a more sophisticated orchestration framework?"
> The pipeline is mostly linear with one fan-out step and one feedback loop. LangGraph is available in the dependencies but the functional approach is more debuggable — you can inspect intermediate dicts at any point. If the system needed dynamic agent selection (e.g., "decide which agent to call based on the learner's response"), LangGraph's state machines would be the right upgrade.

### "How would you productionize this?"
> Three priorities: (1) Replace JSON file storage with a real database — the current approach doesn't survive crashes or support multiple processes. (2) Move long-running pipelines (content generation chains 4+ LLM calls) to background workers with job status polling. (3) Add LLM reliability — retries, fallback models, token budgets, and response caching. The stateless agent design already supports horizontal scaling; the bottleneck is shared state and synchronous execution.

### "How does RAG work in this system?"
> The SearchRagManager follows a search-then-retrieve pattern. When drafting a knowledge point, it constructs a search query from the session title + knowledge point name, runs a DuckDuckGo search, loads the result pages into Documents, chunks them, stores them in Chroma, then does a similarity search to retrieve the most relevant chunks. These chunks are injected into the drafter's prompt as `external_resources`. The key insight is that search results are persisted in the vector store, so repeated queries on similar topics get progressively better retrieval.
