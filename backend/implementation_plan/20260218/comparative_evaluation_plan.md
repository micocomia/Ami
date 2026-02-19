# Comparative Evaluation Plan: GenMentor (Baseline) vs. 5902Group5 (Enhanced)

## Purpose

This plan defines an evaluation suite that runs against **both versions** of the system using inputs that faithfully replicate each version's real onboarding flow, producing side-by-side scores for the MVP presentation. The goal is to quantify specific improvements made in the enhanced version across five dimensions:

1. RAG retrieval quality (RAGAS)
2. Skill gap identification quality (LangSmith LLM-as-a-Judge)
3. Learning plan quality (LangSmith LLM-as-a-Judge)
4. Content generation quality (LangSmith LLM-as-a-Judge)
5. API performance (quantitative)

---

## Version Differences That Affect Evaluation Design

| Dimension | GenMentor (Baseline) | 5902Group5 (Enhanced) |
|---|---|---|
| Proficiency scale | 3 levels: beginner / intermediate / advanced | 4 levels: adds **expert** |
| Learning preferences representation | Free-text `content_style` + `activity_type` | Structured **FSLSM dimensions** (4 continuous scores, −1 to +1) |
| Skill gap assessment | 3-level scale, no metacognitive framing | 4-level scale + **SOLO-informed** goal assessment |
| Learning path sessions | Plain sessions (title, abstract, skills) | Sessions with FSLSM structural fields (`navigation_mode`, `has_checkpoint_challenges`, `thinking_time_buffer_minutes`, etc.) |
| Onboarding seed | **Occupation** selected from dropdown (required); prepended to `learner_information` | **Persona** selected from cards (required); FSLSM vector serialized as text prefix on `learner_information` |
| Fairness / bias tooling | Not present | Bias auditor + fairness validator |
| Auth + persistence | Not present | Auth, behavioral metrics, mastery tracking |
| Agentic plan generation | Not present | `/schedule-learning-path-agentic` |
| Content feedback loop | Not present | `/simulate-content-feedback` |

### How each system constructs `learner_information` at onboarding

Both systems require a seed selection before the user can proceed. The selected seed is prepended to any additional learner text before all API calls are made.

**GenMentor** (`frontend/pages/onboarding.py:149`):
```
learner_information = occupation_label + learner_text + pdf_text
```
Occupation options: Software Engineer, Data Scientist, AI Researcher, Product Manager, UI/UX Designer, Other.

**5902Group5 Enhanced** (`frontend/pages/onboarding.py:200–245`):
```
learner_information = "Learning Persona: {name} (initial FSLSM: processing={p}, perception={pe}, input={i}, understanding={u}). " + pdf_text
```
Persona options: Hands-on Explorer, Reflective Reader, Visual Learner, Conceptual Thinker, Balanced Learner — each with fixed FSLSM seed vectors defined in `main.py` and `frontend/utils/personas.py`.

The profiler prompt explicitly instructs the LLM to preserve the FSLSM seed unless strong contrary evidence exists in the learner's background text (see `modules/learner_profiler/prompts/adaptive_learning_profiler.py:76`). Without a seed, the LLM infers FSLSM from weak text signals and typically produces near-neutral (~0.0) values, making FSLSM-dependent structural fields in sessions and content adaptation undifferentiated and unjudgeable.

### Evaluation strategy

- **Version-specific API inputs**: each system receives `learner_information` constructed exactly as its real onboarding flow does (occupation-prefixed for GenMentor, persona+FSLSM-prefixed for Enhanced). This is required to activate each system's personalization machinery correctly.
- **Neutral judge context**: LLM judge prompts receive only the plain background text (no prefix), so the evaluator sees neutral context without a system-specific fingerprint that could bias scoring.
- **Shared dimensions**: criteria that both systems can be measured against (completeness, coherence, sequencing, accuracy, latency).
- **Enhanced-only dimensions**: additional criteria (FSLSM alignment, SOLO progression, expert-level calibration) that only the enhanced system supports; these become the "improvement delta" metrics for the presentation.
- **Schema normalization**: the LLM judge prompts handle both schemas gracefully; the enhanced system's richer output simply provides more signal for the additional dimensions.

---

## Shared Test Dataset

Use **9 scenarios** (3 learning goals × 3 learner backgrounds). This is sufficient for MVP-level statistical validity while keeping evaluation cost manageable.

### Learning goals

| ID | Learning goal |
|---|---|
| G1 | "I want to learn full-stack web development using React and Node.js" |
| G2 | "I want to master machine learning fundamentals and apply them to real datasets" |
| G3 | "I want to build and deploy a REST API to the cloud" |

### Learner backgrounds + onboarding seed assignments

| ID | Profile description | GenMentor occupation | Enhanced persona | FSLSM seed |
|---|---|---|---|---|
| B1 | **Complete beginner** — CS undergraduate, no prior programming | Software Engineer | Balanced Learner | (0.0, 0.0, 0.0, 0.0) |
| B2 | **Intermediate** — 1–2 years self-taught Python, personal projects | Software Engineer | Hands-on Explorer | (−0.7, −0.5, −0.5, −0.5) |
| B3 | **Career switcher** — 5 years marketing/analytics, self-taught HTML/CSS | Product Manager | Visual Learner | (−0.2, −0.3, −0.8, −0.3) |

**Persona rationale:**
- B1 → Balanced Learner: beginner has no established learning style; a neutral seed avoids imposing a style that hasn't been validated.
- B2 → Hands-on Explorer: self-taught, project-driven learner maps naturally to active/concrete/sequential style.
- B3 → Visual Learner: marketing/analytics background is strongly associated with visual data interpretation.

**Occupation rationale (GenMentor):**
- B1, B2 → Software Engineer: the aspirational/target profession for both learners.
- B3 → Product Manager: best reflects a marketing professional's current role; bridges to tech.

### `learner_information` variants in the dataset

Each scenario in `shared_test_cases.json` carries three fields:

| Field | Used by | Content |
|---|---|---|
| `learner_information` | Judge prompts | Plain background text only — no system-specific prefix |
| `learner_information_genmentor` | GenMentor API calls | `"<occupation> " + background_text` |
| `learner_information_enhanced` | Enhanced API calls | `"Learning Persona: <name> (initial FSLSM: ...). " + background_text` |

### Scenario matrix (9 total)

| Scenario | Goal | Background | GenMentor seed | Enhanced persona |
|---|---|---|---|---|
| S01 | G1 | B1 | Software Engineer | Balanced Learner |
| S02 | G1 | B2 | Software Engineer | Hands-on Explorer |
| S03 | G1 | B3 | Product Manager | Visual Learner |
| S04 | G2 | B1 | Software Engineer | Balanced Learner |
| S05 | G2 | B2 | Software Engineer | Hands-on Explorer |
| S06 | G2 | B3 | Product Manager | Visual Learner |
| S07 | G3 | B1 | Software Engineer | Balanced Learner |
| S08 | G3 | B2 | Software Engineer | Hands-on Explorer |
| S09 | G3 | B3 | Product Manager | Visual Learner |

The full JSON dataset lives at `backend/evals/datasets/shared_test_cases.json`.

**Personas not covered:** Reflective Reader and Conceptual Thinker. These can be added in a post-MVP follow-up evaluation pass.

---

## 1. RAG Quality Evaluation (RAGAS)

### What to evaluate

The `SearchRagManager` → `SearchEnhancedKnowledgeDrafter` pipeline, triggered through `/draft-knowledge-point`. Both systems share the same base RAG implementation; this establishes a quality baseline and validates that the enhanced system did not regress.

### Equivalent endpoint

`POST /draft-knowledge-point` (present in both versions, identical contract)

### Dummy profile design

`/draft-knowledge-point` requires a `learner_profile` argument. Both systems use the profile differently:

- **GenMentor**: passes the profile through to the drafter LLM prompt as context; `learning_preferences` has free-text `content_style` and `activity_type`.
- **Enhanced**: actively extracts FSLSM dimensions from `learning_preferences.fslsm_dimensions` before calling the drafter, using them to generate `visual_formatting_hints` and `processing_perception_hints` that shape the draft prompt.

Each version therefore receives a version-correct dummy profile:

| Field | GenMentor dummy | Enhanced dummy |
|---|---|---|
| `learning_preferences` | `{content_style: "mixed", activity_type: "mixed"}` | `{fslsm_dimensions: {all: 0.0}, additional_notes: null}` |
| `goal_display_name` | not present | `""` (required field, defaults to `""`) |
| `cognitive_status` | empty (no skills) | empty (no skills) |

FSLSM dimensions are set to neutral (0.0) for the enhanced dummy profile. This is intentional: RAG retrieval is query-driven, not persona-driven. Neutral FSLSM values produce generic (non-directional) formatting hints, keeping the comparison focused on retrieval quality rather than style personalization.

### Response structure and context extraction

Both systems return `{"knowledge_draft": {"title": str, "content": str, ...}}`. The `content` field inside `knowledge_draft` is the answer used by RAGAS.

For retrieved contexts:
- **Enhanced**: `knowledge_draft.sources_used` contains the retrieved documents (list of dicts with `page_content`).
- **GenMentor**: no `sources_used` field in `KnowledgeDraft`; the draft content itself is used as the fallback context.

This asymmetry means Context Precision and Context Recall scores for GenMentor are less reliable (single-context fallback), while Enhanced scores are computed against the actual retrieved chunks. This limitation should be noted in the presentation.

### Metrics

| Metric | Applies to | How to compute |
|---|---|---|
| Context Precision | Both | % of top-k retrieved chunks relevant to the query |
| Context Recall | Both | Coverage of ground-truth facts in retrieved context |
| Faithfulness | Both | Claims in draft attributable to retrieved documents |
| Answer Relevancy | Both | Draft relevance to the knowledge point query |

### Test input construction

3 knowledge points per learning goal × 3 goals = 9 fixed RAG evaluation cases (defined in `shared_test_cases.json` under `rag_knowledge_points` and `rag_ground_truths`). Ground truths were constructed manually and cover the key facts expected for each topic.

### Implementation

See `backend/evals/eval_rag.py`.

### Expected presentation output

Side-by-side RAGAS scores (baseline vs. enhanced) across the 4 metrics, averaged over all 9 cases.

---

## 2. Skill Gap Evaluation (LangSmith LLM-as-a-Judge)

### What to evaluate

The pipeline: `LearningGoalRefiner` → `SkillRequirementMapper` → `SkillGapIdentifier`, triggered through:

- `POST /refine-learning-goal` (both)
- `POST /identify-skill-gap-with-info` (both)

### API input

Both calls use `learner_information_<version>` (occupation-prefixed for GenMentor, persona+FSLSM-prefixed for Enhanced). The judge receives only the plain `learner_information` background text.

### Evaluation dimensions

| Dimension | What to assess | Both / Enhanced-only |
|---|---|---|
| Skill Identification Completeness | Are all relevant skills for the goal identified? | **Both** |
| Gap Calibration | Are inferred current levels reasonable given the background? | **Both** |
| Goal Refinement Quality | Are refined goals specific, actionable, and non-drifting? | **Both** |
| Confidence Score Validity | Do confidence scores correlate with information availability? | **Both** |
| Expert-Level Calibration | When background warrants "expert", is it correctly assigned? | **Enhanced-only** |
| SOLO Level Accuracy | Are SOLO-grounded assessments of current proficiency correct? | **Enhanced-only** |

### Judge prompt (shared dimensions, version-agnostic)

```
You are evaluating a Skill Gap Identification system.

Learning Goal: {refined_goal}
Learner Background: {learner_information}
Identified Skill Requirements: {skill_requirements_json}
Identified Skill Gaps: {skill_gaps_json}

Rate 1–5 for each of the following. Respond with JSON only.
{
  "completeness": {"score": int, "reason": str},
  "gap_calibration": {"score": int, "reason": str},
  "goal_refinement_quality": {"score": int, "reason": str},
  "confidence_validity": {"score": int, "reason": str}
}

Scoring rubric:
- completeness: 1=major skills missing, 5=all relevant skills present
- gap_calibration: 1=proficiency levels wildly off, 5=well-calibrated to background
- goal_refinement_quality: 1=vague/drifting, 5=specific and actionable
- confidence_validity: 1=confidence scores random, 5=correlated with information quality
```

### Judge prompt extension (enhanced-only dimensions)

```
Additionally, for the enhanced version:
{
  "expert_calibration": {"score": int, "reason": str},
  "solo_level_accuracy": {"score": int, "reason": str}
}

SOLO rubric for reference:
- Prestructural: no relevant knowledge
- Unistructural (beginner): one relevant aspect known
- Multistructural (intermediate): several aspects known but not connected
- Relational (advanced): aspects integrated into a coherent whole
- Extended Abstract (expert): can generalise beyond the domain

- expert_calibration: 1=expert never assigned even when warranted, 5=expert correctly used
- solo_level_accuracy: 1=SOLO levels inconsistent with background, 5=precisely SOLO-grounded
```

### Implementation

See `backend/evals/eval_skill_gap.py`.

---

## 3. Learning Plan Evaluation (LangSmith LLM-as-a-Judge)

### What to evaluate

`LearningPathScheduler`, triggered through:

- `POST /schedule-learning-path` (both)
- `POST /schedule-learning-path-agentic` (enhanced-only, add as bonus comparison metric)

### Input construction

For each scenario, the evaluation runs the full onboarding pipeline end-to-end on each system using its version-specific `learner_information`:

1. `POST /identify-skill-gap-with-info` with `learner_information_<version>`
2. `POST /create-learner-profile-with-info` with `learner_information_<version>` + skill gaps from step 1
3. `POST /schedule-learning-path` with the profile from step 2

This is intentional — we evaluate the full pipeline, not an isolated sub-component. GenMentor produces a profile with free-text preferences; the Enhanced system produces a profile with FSLSM dimensions seeded from the persona prefix. The FSLSM-structural judge dimensions are then only applied to the Enhanced version's output where those fields exist.

### Evaluation dimensions

| Dimension | What to assess | Both / Enhanced-only |
|---|---|---|
| Pedagogical Sequencing | Prerequisites before advanced content; builds incrementally | **Both** |
| Skill Coverage | All identified skill gaps map to at least one session | **Both** |
| Scope Appropriateness | Realistic depth given the number of sessions requested | **Both** |
| Session Abstraction Quality | Session titles/abstracts are meaningful and non-redundant | **Both** |
| FSLSM Structural Alignment | Session structural fields (`navigation_mode`, `checkpoint_challenges`, etc.) match learner's FSLSM profile | **Enhanced-only** |
| SOLO Outcome Progression | `desired_outcome_when_completed` proficiency levels follow a logical progression | **Enhanced-only** |

### Judge prompt (shared dimensions)

```
You are evaluating a personalized learning plan.

Learner Background: {learner_information}
Skill Gaps to Address: {skill_gaps_json}
Requested Session Count: {session_count}
Generated Learning Path: {learning_path_json}

Rate 1–5 for each. Respond with JSON only.
{
  "pedagogical_sequencing": {"score": int, "reason": str},
  "skill_coverage": {"score": int, "reason": str},
  "scope_appropriateness": {"score": int, "reason": str},
  "session_abstraction_quality": {"score": int, "reason": str}
}
```

### Judge prompt extension (enhanced-only)

```
Also evaluate:
FSLSM Dimensions: {fslsm_dimensions}

{
  "fslsm_structural_alignment": {"score": int, "reason": str},
  "solo_outcome_progression": {"score": int, "reason": str}
}

FSLSM structural alignment guide:
- Active learner (processing ≤ -0.5): should have has_checkpoint_challenges=true
- Reflective learner (processing ≥ 0.5): should have thinking_time_buffer_minutes > 0
- Sequential learner (understanding ≤ -0.5): navigation_mode should be "linear"
- Global learner (understanding ≥ 0.5): navigation_mode should be "free"

SOLO progression: desired_outcome_when_completed proficiency levels should not skip
levels (beginner → intermediate → advanced → expert), or justify if they do.
```

### Implementation

See `backend/evals/eval_plan.py`.

---

## 4. Content Generator Evaluation (LangSmith LLM-as-a-Judge)

### What to evaluate

`LearningContentCreator`, triggered through:

- `POST /tailor-knowledge-content` — end-to-end content for a session (both versions)
- Generated quizzes (called inside the pipeline)

Content is evaluated for **session 1 only** per scenario to control API cost.

### Input construction

Same full pipeline as the Learning Plan evaluation, extended with a `/tailor-knowledge-content` call for the first session. Uses `learner_information_<version>` throughout; judge receives plain `learner_information`.

### Evaluation dimensions

| Dimension | What to assess | Both / Enhanced-only |
|---|---|---|
| Cognitive Level Match | Content complexity appropriate to the learner's current level | **Both** |
| Factual Accuracy | Content is factually correct (cross-referenced with RAG sources) | **Both** |
| Quiz Alignment | Quiz questions test knowledge points in the content | **Both** |
| Engagement Quality | Clear structure, appropriate depth, motivating examples | **Both** |
| FSLSM Content Adaptation | Writing style / examples / structure adapted to FSLSM preferences | **Enhanced-only** |
| SOLO Cognitive Load Alignment | Explanations target the learner's current SOLO level | **Enhanced-only** |

### Judge prompt (shared dimensions)

```
You are evaluating personalized learning content.

Learner Background: {learner_information}
Session Goal: {session_title}
Knowledge Points Covered: {knowledge_points_json}
Generated Content (markdown excerpt, first 3000 chars): {content_excerpt}
Generated Quizzes: {quizzes_json}

Rate 1–5 for each. Respond with JSON only.
{
  "cognitive_level_match": {"score": int, "reason": str},
  "factual_accuracy": {"score": int, "reason": str},
  "quiz_alignment": {"score": int, "reason": str},
  "engagement_quality": {"score": int, "reason": str}
}

Scoring rubric:
- cognitive_level_match: 1=assumes far more/less than learner knows, 5=perfectly calibrated
- factual_accuracy: 1=significant errors, 5=fully accurate
- quiz_alignment: 1=quizzes unrelated to content, 5=directly test every knowledge point
- engagement_quality: 1=dry/confusing/unsupported, 5=clear, structured, motivating
```

### Judge prompt extension (enhanced-only)

```
Also evaluate (enhanced version only):
FSLSM Dimensions: {fslsm_dimensions}
Current SOLO Level: {current_solo_level}

{
  "fslsm_content_adaptation": {"score": int, "reason": str},
  "solo_cognitive_alignment": {"score": int, "reason": str}
}

FSLSM content adaptation guide:
- Visual learner (input ≤ -0.5): should include diagrams, tables, visual examples
- Verbal learner (input ≥ 0.5): text-heavy, narrative explanations
- Active learner (processing ≤ -0.5): hands-on exercises, code challenges, interactive elements
- Reflective learner (processing ≥ 0.5): reflection prompts, analysis tasks, compare-and-contrast
- Sensing learner (perception ≤ -0.5): concrete examples before abstract concepts
- Intuitive learner (perception ≥ 0.5): theory and concepts before concrete examples

SOLO cognitive alignment:
- Beginner (unistructural): simple definitions, one concept at a time
- Intermediate (multistructural): multiple concepts side-by-side, lists, comparisons
- Advanced (relational): integration, cause-effect, applying concepts to scenarios
- Expert (extended abstract): generalisation, critical evaluation, novel applications
```

### Implementation

See `backend/evals/eval_content.py`.

---

## 5. API Performance (Quantitative)

### What to evaluate

Latency and error rate for equivalent pipeline stages on both systems, called with their version-specific `learner_information_<version>` inputs.

### Equivalent pipeline stages

| Stage | GenMentor endpoint | Enhanced endpoint |
|---|---|---|
| Goal refinement | `POST /refine-learning-goal` | `POST /refine-learning-goal` |
| Skill gap identification | `POST /identify-skill-gap-with-info` | `POST /identify-skill-gap-with-info` |
| Profile creation | `POST /create-learner-profile-with-info` | `POST /create-learner-profile-with-info` |
| Learning path scheduling | `POST /schedule-learning-path` | `POST /schedule-learning-path` |
| Knowledge point exploration | `POST /explore-knowledge-points` | `POST /explore-knowledge-points` |
| Full content generation | `POST /tailor-knowledge-content` | `POST /tailor-knowledge-content` |
| Chat with tutor | `POST /chat-with-tutor` | `POST /chat-with-tutor` |

### Metrics collected per endpoint per version

| Metric | What it measures |
|---|---|
| `p50_latency_ms` | Median response time |
| `p95_latency_ms` | 95th-percentile response time (tail latency) |
| `error_rate_pct` | % of requests returning 4xx/5xx |

### Run protocol

- Use all 9 scenarios as test inputs (9 calls per endpoint per version) with their respective `learner_information_<version>` payloads.
- Run sequentially (not concurrent) to avoid rate-limit interference.
- LangSmith tracing enabled on both (`LANGCHAIN_TRACING_V2=true`) for token count capture.

### Implementation

See `backend/evals/eval_api_perf.py`.

---

## Reporting Format

After running all evaluations, `backend/evals/run_all.py` produces `backend/evals/results/comparison_report.json` and a human-readable `comparison_report.md`. The report structure:

```
## Comparative Evaluation Summary

### 1. RAG Quality (RAGAS, 0–1 scale)
| Metric            | GenMentor | 5902Group5 | Delta  |
|---|---|---|---|
| Context Precision | X.XX      | X.XX       | +X.XX  |
| Context Recall    | ...       | ...        | ...    |
| Faithfulness      | ...       | ...        | ...    |
| Answer Relevancy  | ...       | ...        | ...    |

### 2. Skill Gap Quality (LLM-Judge, 1–5 scale)
| Dimension                       | GenMentor | 5902Group5 | Delta |
|---|---|---|---|
| Completeness                    | X.X       | X.X        | +X.X  |
| Gap Calibration                 | ...       | ...        | ...   |
| Goal Refinement Quality         | ...       | ...        | ...   |
| Confidence Validity             | ...       | ...        | ...   |
| Expert Calibration (enhanced)   | N/A       | X.X        | —     |
| SOLO Level Accuracy (enhanced)  | N/A       | X.X        | —     |

### 3. Learning Plan Quality (LLM-Judge, 1–5 scale)
| Dimension                              | GenMentor | 5902Group5 | Delta |
...

### 4. Content Quality (LLM-Judge, 1–5 scale)
| Dimension                             | GenMentor | 5902Group5 | Delta |
...

### 5. API Performance
| Endpoint               | GenMentor p50 | GenMentor p95 | 5902Group5 p50 | 5902Group5 p95 | p50 Delta |
...

### Overall Summary
| Version               | Shared-Dimension Average (1–5) |
|---|---|
| GenMentor (Baseline)  | X.XX |
| 5902Group5 (Enhanced) | X.XX |
| Delta                 | +X.XX |
```

---

## Directory Structure

```
backend/
├── evals/
│   ├── __init__.py
│   ├── config.py                        # BaseURL + model config for both systems
│   ├── datasets/
│   │   └── shared_test_cases.json       # 9 scenarios with per-version learner_information variants
│   ├── eval_rag.py                      # RAGAS evaluation (both systems)
│   ├── eval_skill_gap.py                # Skill gap LLM-judge (shared + enhanced dimensions)
│   ├── eval_plan.py                     # Learning plan LLM-judge
│   ├── eval_content.py                  # Content LLM-judge
│   ├── eval_api_perf.py                 # API performance (latency + error rate)
│   ├── run_all.py                       # Master runner → comparison_report.md
│   ├── utils/
│   │   ├── llm_judge.py                 # Shared LLM-as-a-judge helper
│   │   ├── schema_adapter.py            # Normalize GenMentor ↔ Enhanced outputs
│   │   └── timing.py                    # Timed HTTP request wrapper
│   └── results/                         # Output directory (gitignored)
│       ├── comparison_report.json
│       └── comparison_report.md
```

---

## Dependencies

```
# Already in backend/requirements.txt
ragas>=0.2.0          # RAGAS evaluation framework
datasets>=2.14.0      # HuggingFace Datasets (explicit dep; also a ragas transitive dep)
httpx==0.28.1         # HTTP client for API calls (already present)
langsmith==0.6.7      # LangSmith tracing (already present)
```

No new dependencies need to be installed — `ragas` and `datasets` were added to `requirements.txt` during planning.

---

## Environment Variables Required

```bash
# Both systems must be running locally (or on accessible hosts)
GENMENTOR_BASE_URL=http://localhost:8000
ENHANCED_BASE_URL=http://localhost:8001

# LLM provider for judge calls
OPENAI_API_KEY=...          # judge uses gpt-4o-mini for cost efficiency
# or
ANTHROPIC_API_KEY=...       # judge uses claude-haiku-4-5

# LangSmith tracing (optional but recommended)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=genmentor-eval
```

---

## Execution Steps for MVP Presentation

```bash
# 1. Start both servers (in separate terminals)
cd GenMentor/backend && uvicorn main:app --port 8000
cd 5902Group5/backend && uvicorn main:app --port 8001

# 2a. Quick run — skip RAG, run 3 representative scenarios (one per background type)
cd 5902Group5/backend
OPENAI_API_KEY=... python -m evals.run_all --skip-rag --scenarios S01,S05,S09

# 2b. Full run — all 9 scenarios, all 5 evaluation phases
OPENAI_API_KEY=... python -m evals.run_all

# 3. View report
cat evals/results/comparison_report.md
```

Total estimated runtime: 20–30 minutes for the full run (dominated by LLM API calls across 9 scenarios × 4 eval categories, each running the full onboarding + content pipeline end-to-end).
