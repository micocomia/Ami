# Evaluation Metrics Plan for Ami

## Overview

This document outlines a possible implementation plan for evaluation metrics across four categories: RAG retrieval quality, Skill Gap agent quality, Learning Plan & Content generation quality, and API performance.

---

## 1. RAG Retrieval Evaluation (RAGAS Metrics)

### What to evaluate
The `SearchRagManager` pipeline in `backend/base/search_rag.py` — specifically how well retrieved web content supports the knowledge drafting step in `SearchEnhancedKnowledgeDrafter`.

### Metrics (RAGAS framework)

| Metric | What it measures | How to compute |
|---|---|---|
| **Context Precision** | Are the retrieved chunks relevant to the query? | Given a query (learning goal + knowledge point), score how many of the top-k retrieved documents are actually relevant. |
| **Context Recall** | Does the retrieved context cover all necessary information? | Compare retrieved content against a reference answer (ground truth) to see if all required facts are present. |
| **Faithfulness** | Is the generated content grounded in retrieved context? | Check whether claims in the `KnowledgeDraft` output can be attributed to the retrieved documents. |
| **Answer Relevancy** | Is the generated answer relevant to the original question? | Score how well the final drafted content addresses the original knowledge point query. |

### Possible implementation approach

1. **Build a golden dataset** of ~30–50 evaluation examples:
   - Each example: `(learning_goal, session_title, knowledge_point_name)` → expected key facts/concepts that should be covered.
   - Can be constructed manually or semi-automatically using expert-written content for common topics (e.g., "Python decorators", "REST API design").

2. **Integrate the `ragas` library** (already compatible with LangChain):
   ```
   pip install ragas
   ```
   - RAGAS works directly with LangChain `Document` objects, which the system already produces from `SearchRagManager.retrieve()`.

3. **Create an evaluation script** (e.g., `backend/evals/eval_rag.py`):
   - For each test case, run `SearchRagManager.invoke(query)` to get retrieved docs.
   - Run `SearchEnhancedKnowledgeDrafter` to get the generated draft.
   - Feed `(question, answer, contexts, ground_truth)` into RAGAS `evaluate()`.
   - Aggregate scores across the dataset.

4. **Parameterize and compare**:
   - Vary `search.max_results` (3 vs 5 vs 10).
   - Vary `rag.chunk_size` (500 vs 1000 vs 2000).
   - Vary `rag.num_retrieval_results` (3 vs 5 vs 10).
   - Vary embedding models (all-mpnet-base-v2 vs other sentence-transformers).
   - Compare search providers (DuckDuckGo vs Serper vs Brave).

5. **Report format**: Table of metric scores per configuration, enabling data-driven tuning of RAG parameters.

### Considerations
- Ground truth construction is the main bottleneck — consider using a strong LLM (GPT-4o) to generate reference answers, then having a human verify them.
- RAGAS metrics themselves use LLM calls, so budget for evaluation API costs.
- Web search results are non-deterministic; consider caching search results for reproducible evaluation runs.

---

## 2. Skill Gap Agent Evaluation (LLM-as-a-Judge via LangSmith)

### What to evaluate
The three-stage pipeline: `SkillRequirementMapper` → `SkillGapIdentifier` → `LearningGoalRefiner` in `backend/modules/skill_gap/`.

### Evaluation dimensions

| Dimension | What to assess | Example criteria |
|---|---|---|
| **Skill Identification Completeness** | Does the mapper identify all relevant skills for the goal? | "Learn full-stack web dev" should include frontend, backend, database, deployment — not just "JavaScript". |
| **SOLO Level Accuracy** | Is the assessed current proficiency level correct given the learner profile? | A learner with "3 years Python, built REST APIs" should not be assessed as `beginner` in Python. |
| **Gap Calibration** | Are the gaps between current and required levels reasonable? | The gap should reflect genuine learning needs, not over/under-estimate. |
| **Goal Refinement Quality** | Are refined goals specific, actionable, and aligned with the original intent? | Vague "learn ML" should become specific sub-goals, not drift to unrelated topics. |
| **Confidence Score Validity** | Do confidence scores correlate with information availability? | Gaps inferred from explicit resume data should have higher confidence than gaps inferred from absence of information. |

### Possible implementation approach

1. **Build evaluation cases** (~20–30):
   - Each case: `(learning_goal, learner_info_text, optional_resume_text)` → expected skill requirements + expected gaps.
   - Cover a range of scenarios:
     - Complete beginner with no background.
     - Experienced professional switching domains.
     - Intermediate learner with partial overlap.
     - Learner with detailed resume vs. minimal info.

2. **Set up LangSmith evaluation**:
   - The project already has `langsmith` v0.6.7 as a dependency.
   - Create a LangSmith dataset with the evaluation cases.
   - Define custom evaluators (LLM-as-a-judge) for each dimension above.

3. **Evaluator prompt design** (one per dimension):
   ```
   You are evaluating a Skill Gap Identification system.

   Given:
   - Learning Goal: {goal}
   - Learner Background: {learner_info}
   - System Output (Identified Skills): {skill_requirements}
   - System Output (Skill Gaps): {skill_gaps}

   Rate the following on a 1-5 scale:
   1. Completeness: Are all relevant skills identified? (1=major gaps, 5=comprehensive)
   2. SOLO Accuracy: Are the proficiency assessments correct? (1=wildly off, 5=spot-on)
   3. Gap Calibration: Are the learning gaps reasonable? (1=unreasonable, 5=well-calibrated)

   Provide a score and brief justification for each.
   ```

4. **Run evaluations via LangSmith**:
   - Use `langsmith.evaluation.evaluate()` with custom evaluator functions.
   - Each evaluator calls an LLM with the structured prompt above.
   - Track results in LangSmith dashboard for trend analysis.

5. **Ablation studies**:
   - With vs. without resume/additional information.
   - Different LLM models (GPT-4o vs Claude vs smaller models).
   - Impact of the goal refinement step on downstream quality.

### Considerations
- SOLO taxonomy correctness is hard for a judge LLM to assess without domain expertise — consider providing the SOLO rubric in the evaluator prompt.
- Inter-rater reliability: run each evaluation 3 times and average to reduce LLM judge variance.
- The existing `test_solo_taxonomy.py` tests validate schema correctness but not semantic quality — this evaluation fills that gap.

---

## 3. Learning Plan & Content Generator Evaluation (LLM-as-a-Judge via LangSmith)

### What to evaluate
- `LearningPathScheduler` in `backend/modules/learning_plan_generator/`
- `LearningContentCreator` pipeline in `backend/modules/content_generator/`

### 3a. Learning Plan Evaluation

| Dimension | What to assess | Criteria |
|---|---|---|
| **Pedagogical Sequencing** | Is the session order logical? | Prerequisites before advanced topics; builds incrementally. |
| **FSLSM Alignment** | Does the plan reflect learning style preferences? | Active learner → hands-on sessions early; Visual learner → diagram-heavy content planned. |
| **Skill Coverage** | Does the plan address all identified skill gaps? | Every skill gap should map to at least one session's `desired_outcome`. |
| **SOLO Progression** | Do desired outcomes follow SOLO progression? | Sessions should progress from unistructural → multistructural → relational → extended abstract. |
| **Scope Appropriateness** | Is the plan realistic given the number of sessions? | Not too shallow (surface-level) or too ambitious (impossible in N sessions). |

### 3b. Content Evaluation

| Dimension | What to assess | Criteria |
|---|---|---|
| **Cognitive Level Match** | Does content match the learner's current SOLO level? | Beginner content shouldn't assume relational understanding. |
| **FSLSM Adaptation** | Is content style adapted to preferences? | Visual learner gets diagrams/examples; Reflective learner gets analysis prompts. |
| **Factual Accuracy** | Is the content factually correct? | Cross-reference with RAG sources (overlaps with RAGAS Faithfulness). |
| **Quiz Alignment** | Do quizzes test what the content teaches? | Questions should map to knowledge points covered, at appropriate difficulty. |
| **Engagement Quality** | Is the content engaging and well-structured? | Clear structure, appropriate depth, motivating examples. |

### Possible implementation approach

1. **Build evaluation scenarios** (~15–20):
   - Use the existing 5 personas (Hands-on Explorer, Reflective Reader, Visual Learner, Conceptual Thinker, Balanced Learner) defined in the personas config.
   - Cross with 3–4 learning goals at different levels.
   - This gives a matrix of ~15–20 persona × goal combinations.

2. **End-to-end pipeline runs**:
   - For each scenario, run the full pipeline: skill gap → profile → learning path → content.
   - Capture all intermediate outputs for evaluation.

3. **LangSmith evaluation setup**:
   - Create separate datasets for plan evaluation and content evaluation.
   - Define evaluator prompts for each dimension.

4. **Plan evaluator prompt example**:
   ```
   You are evaluating a personalized learning plan.

   Learner Profile:
   - FSLSM Processing: {processing} (negative=active, positive=reflective)
   - FSLSM Perception: {perception} (negative=sensing, positive=intuitive)
   - FSLSM Input: {input} (negative=visual, positive=verbal)
   - FSLSM Understanding: {understanding} (negative=sequential, positive=global)
   - Current SOLO Level: {current_levels}
   - Skill Gaps: {gaps}

   Generated Learning Plan:
   {learning_path_json}

   Rate on 1-5:
   1. Pedagogical Sequencing
   2. FSLSM Alignment
   3. Skill Coverage
   4. SOLO Progression
   5. Scope Appropriateness

   For each, provide score + one-sentence justification.
   ```

5. **Content evaluator prompt example**:
   ```
   You are evaluating personalized learning content.

   Learner Profile: {profile_summary}
   Session Goal: {session_title}
   Knowledge Points Covered: {knowledge_points}

   Generated Content:
   {content_markdown}

   Generated Quizzes:
   {quizzes_json}

   Rate on 1-5:
   1. Cognitive Level Match
   2. FSLSM Adaptation
   3. Factual Accuracy
   4. Quiz Alignment
   5. Engagement Quality
   ```

6. **Leverage existing Learner Simulator**:
   - The system already has `LearnerBehaviorSimulator` and feedback simulators.
   - Compare LLM-judge scores against simulator feedback scores (`progression`, `engagement`, `personalization`) for correlation analysis.
   - This validates whether the simulator's feedback loop is actually driving quality improvements.

7. **Iterative refinement evaluation**:
   - Run the `/iterative-refine-path` endpoint and track how scores change across iterations 1–5.
   - Determine if the refinement loop converges and whether more iterations yield diminishing returns.

### Considerations
- Persona diversity is important — the 5 built-in personas provide good FSLSM coverage but may not cover edge cases.
- Content evaluation is expensive (long documents); consider evaluating a subset of sessions rather than all.
- Quiz alignment can also be assessed quantitatively by checking if quiz questions reference concepts in the content (keyword overlap, embedding similarity).

---

## 4. API Performance Metrics (Quantitative)

### What to evaluate
All endpoints in `backend/main.py`, with focus on the LLM-heavy pipelines.

### Metrics

| Metric | What it measures | Collection method |
|---|---|---|
| **Latency (p50, p95, p99)** | Response time distribution | Middleware timing |
| **Error Rate** | % of 4xx/5xx responses | Response status tracking |
| **LLM Call Count** | Number of LLM invocations per request | LangSmith trace analysis or middleware counter |
| **LLM Token Usage** | Input/output tokens per request | LangChain callback handler |
| **Throughput** | Requests per second under load | Load testing tool |
| **Search Latency** | Time spent in web search vs. LLM generation | Sub-component timing |
| **RAG Pipeline Latency** | Breakdown: search → load → chunk → embed → retrieve | Per-stage timing |

### Possible implementation approach

1. **FastAPI middleware for request-level metrics**:
   - Add a middleware to `main.py` that logs:
     - Endpoint path
     - Request timestamp
     - Response status code
     - Total duration
   - Store in a structured log (JSON lines) or push to a metrics backend.

2. **LangSmith tracing** (already partially set up):
   - The project already depends on `langsmith` v0.6.7.
   - Enable tracing by setting `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY`.
   - LangSmith automatically captures:
     - Per-LLM-call latency
     - Token usage (input/output)
     - Chain/agent execution traces
     - Error traces
   - Use the LangSmith dashboard to analyze traces.

3. **Per-pipeline timing breakdown**:
   - Instrument the key pipelines with timing decorators/context managers:
     - Skill Gap pipeline: `refine_goal` → `map_requirements` → `identify_gaps` (3 LLM calls)
     - Content pipeline: `explore_knowledge` → `search_rag` → `draft` → `integrate` → `quiz` (5+ LLM calls)
     - Learning path: `schedule` → (optional: `simulate` → `refine`) × N iterations

4. **Load testing with Locust or k6**:
   - Create scenarios that exercise the main user flows:
     - Onboarding flow (goal → skill gap → profile): ~3 LLM calls
     - Path generation: ~1–2 LLM calls
     - Content generation for one session: ~5+ LLM calls
     - Chat with tutor: ~1 LLM call + optional RAG
   - Measure how the system handles concurrent users.
   - Identify bottlenecks (likely the LLM API rate limits).

5. **Token cost tracking**:
   - Track cumulative token usage per user session.
   - Estimate cost per onboarding, per session content generation, per chat interaction.
   - Use LangChain's `get_openai_callback()` context manager for OpenAI models.

6. **Error categorization**:
   - LLM parsing errors (Pydantic validation failures on structured output).
   - Search provider failures (DuckDuckGo rate limits, timeouts).
   - Document loading failures (unreachable URLs, parsing errors).
   - Auth errors (token expiry, invalid credentials).

### Considerations
- LLM latency dominates overall request latency — API performance is largely bottlenecked by the LLM provider.
- Parallel knowledge drafting (`ThreadPoolExecutor` with 8 workers) affects throughput differently than sequential pipelines.
- Consider testing with different LLM providers to compare latency/cost tradeoffs.

---

## Suggested Evaluation Infrastructure

### Directory structure
```
backend/
├── evals/
│   ├── __init__.py
│   ├── datasets/               # Golden datasets (JSON/JSONL)
│   │   ├── rag_test_cases.json
│   │   ├── skill_gap_test_cases.json
│   │   └── plan_content_scenarios.json
│   ├── eval_rag.py             # RAGAS evaluation script
│   ├── eval_skill_gap.py       # Skill gap LLM-judge evaluation
│   ├── eval_plan_content.py    # Plan & content LLM-judge evaluation
│   ├── eval_api_perf.py        # API performance benchmarking
│   ├── evaluators/             # Custom LangSmith evaluator functions
│   │   ├── skill_gap_judge.py
│   │   ├── plan_judge.py
│   │   └── content_judge.py
│   └── utils/
│       ├── timing.py           # Timing decorators/middleware
│       └── dataset_builder.py  # Helpers for building golden datasets
```

### Dependencies to add
```
ragas>=0.2.0          # RAGAS evaluation framework
locust>=2.0           # Load testing (optional, for API perf)
```

### Execution approach
- **CI integration**: Run a subset of evaluations (fast, cached) on every PR.
- **Full evaluation**: Run the complete suite periodically or before releases, since LLM-based evaluation is slow and costly.
- **Results tracking**: Use LangSmith dashboard for LLM-judge metrics; use a simple CSV/JSON log for API performance over time.

---

## Summary Table

| Category | Method | Tool | Key Metrics | Dataset Size |
|---|---|---|---|---|
| RAG Quality | Automated (RAGAS) | `ragas` library | Context Precision, Context Recall, Faithfulness, Answer Relevancy | 30–50 cases |
| Skill Gap Quality | LLM-as-a-Judge | LangSmith | Completeness, SOLO Accuracy, Gap Calibration, Goal Refinement | 20–30 cases |
| Plan & Content Quality | LLM-as-a-Judge | LangSmith | Sequencing, FSLSM Alignment, Coverage, SOLO Progression, Quiz Alignment | 15–20 scenarios |
| API Performance | Quantitative | Middleware + LangSmith + Locust | Latency, Error Rate, Token Usage, Throughput | N/A (runtime) |
