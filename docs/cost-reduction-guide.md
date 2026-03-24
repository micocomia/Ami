# Ami — Cost Reduction Guide

This guide is for the technical team managing the Ami backend. It explains what drives API costs and describes every configuration lever available to reduce spend — without requiring code changes.

All settings live in a single file: **`backend/config/default.yaml`**. After editing it, restart the backend for changes to take effect.

---

## What Drives the Cost

OpenAI API charges are billed per token (roughly per word) sent to and received from the model. Ami's costs come from three sources:

| Source | Model used | Relative cost |
|---|---|---|
| **Main reasoning agents** (skill gap analysis, learning path scheduling, session content generation) | `gpt-4o` | High |
| **Quality-check and evaluation agents** (reflexion loops, plan simulators, draft evaluators) | `gpt-4o-mini` | Low (~100× cheaper than `gpt-4o`) |
| **Background prefetch** — Ami pre-generates the next session while the learner works through the current one | Same as above | Multiplies content generation cost |

Web search (DuckDuckGo) and audio narration (Microsoft Edge TTS) are **free** — they do not contribute to API costs.

---

## Quick Reference

All levers below are set in `backend/config/default.yaml`.

| # | What it controls | Config key | Default | Low-cost value | Cost impact |
|---|---|---|---|---|---|
| 1 | Model used for all main agents | `llm.model_name` | `gpt-4o` | `gpt-4o-mini` | **High** |
| 2 | Background session pre-generation | `prefetch.enabled` | `true` | `false` | **High** |
| 3 | Content quality check rounds | `content_generation.max_quality_rounds` | `2` | `1` | **High** |
| 4 | Knowledge points explored per session | `content_generation.max_knowledge_points` | `4` | `2` | **Medium** |
| 5 | Learning plan reflexion passes | `learning_plan.max_refinements` | `1` | `0` | **Medium** |
| 6 | Skill gap reflexion iterations | `skill_gap.max_eval_iterations` | `2` | `1` | **Medium** |
| 7 | Goal clarification iterations | `skill_gap.max_goal_iterations` | `2` | `1` | **Low** |
| 8 | Media search in chatbot | `chatbot.enable_media_search` | `true` | `false` | **Low** |
| 9 | Documents retrieved per RAG query | `rag.num_retrieval_results` | `5` | `2` | **Low** |

---

## Lever Details

### 1. Model for main agents — `llm.model_name`

**What it does:** All of Ami's primary reasoning steps (identifying skill gaps, generating a learning path, producing session content, running the chatbot) use this model.

**Trade-off:** `gpt-4o-mini` is significantly cheaper and faster, but produces somewhat less nuanced output. In testing, most learners do not notice a meaningful quality difference for standard topics. The difference is more visible on complex or highly technical subject matter.

**How to change:**
```yaml
llm:
  model_name: gpt-4o-mini   # changed from gpt-4o
```

---

### 2. Background session pre-generation — `prefetch.enabled`

**What it does:** While a learner works through the current session, Ami silently generates the next one in the background. This makes session transitions feel instant.

**Trade-off:** Disabling prefetch means the learner will wait for content to generate when they move to the next session (typically 2–5 minutes). There is no impact on content quality.

**How to change:**
```yaml
prefetch:
  enabled: false   # changed from true
```

---

### 3. Content quality check rounds — `content_generation.max_quality_rounds`

**What it does:** After generating lesson content, Ami runs up to this many rounds of self-evaluation and repair. Each round involves additional LLM calls to check the document and fix any issues found.

**Trade-off:** Reducing to `1` means the content is checked once rather than twice. For most topics, one round is sufficient. Occasional minor structural issues that would have been caught in the second round may appear in the final document.

**How to change:**
```yaml
content_generation:
  max_quality_rounds: 1   # changed from 2
```

---

### 4. Knowledge points per session — `content_generation.max_knowledge_points`

**What it does:** Controls how many distinct concepts Ami explores and drafts content for in a single learning session. More knowledge points means a longer, richer session — and more LLM calls to generate and evaluate each one.

**Trade-off:** Reducing to `2` produces shorter, more focused sessions. Learners cover fewer concepts per session but each is explored in more depth. This also increases the total number of sessions in a learning path.

**How to change:**
```yaml
content_generation:
  max_knowledge_points: 2   # changed from 4
```

---

### 5. Learning plan reflexion passes — `learning_plan.max_refinements`

**What it does:** After generating an initial learning path, Ami evaluates it using a simulated learner and refines the plan if the evaluation finds issues. This parameter controls how many refinement passes are allowed.

**Trade-off:** Setting to `0` disables the refinement loop entirely — the first generated plan is used directly. Plans are generally good on the first attempt; the refinement loop catches edge cases like mismatched difficulty or poor session ordering.

**How to change:**
```yaml
learning_plan:
  max_refinements: 0   # changed from 1
```

---

### 6. Skill gap reflexion iterations — `skill_gap.max_eval_iterations`

**What it does:** After identifying skill gaps, Ami runs an evaluator that checks the result for completeness and accuracy, then re-runs the analysis with feedback if needed. This parameter controls how many analysis-evaluate cycles are allowed.

**Trade-off:** Reducing to `1` means Ami generates skill gaps once without a follow-up evaluation pass. The output is still grounded in the learner's goal and background — it just skips the automated quality check.

**How to change:**
```yaml
skill_gap:
  max_eval_iterations: 1   # changed from 2
```

---

### 7. Goal clarification iterations — `skill_gap.max_goal_iterations`

**What it does:** If a learner's stated goal is vague, Ami attempts to refine it into a clearer target before proceeding. This parameter controls how many clarification attempts are made.

**Trade-off:** Reducing to `1` means Ami makes one clarification attempt instead of two. Most goals are resolved in the first attempt; this saves one round of LLM calls for vague goals.

**How to change:**
```yaml
skill_gap:
  max_goal_iterations: 1   # changed from 2
```

---

### 8. Media search in chatbot — `chatbot.enable_media_search`

**What it does:** When enabled, Ami's chatbot can search for and recommend relevant images, videos, or diagrams in response to learner questions. Each search involves additional LLM calls to filter and rank results.

**Trade-off:** Disabling media search means the chatbot responds with text and session content only. It cannot suggest supplementary visual or video resources. Text-based answers are unaffected.

**How to change:**
```yaml
chatbot:
  enable_media_search: false   # changed from true
```

---

### 9. Documents retrieved per RAG query — `rag.num_retrieval_results`

**What it does:** When Ami retrieves context from its indexed knowledge base (e.g., verified course materials), it fetches this many documents per query. More documents provide richer context but increase the number of tokens sent to the model.

**Trade-off:** Reducing to `2` fetches less context per retrieval call. For well-defined topics with focused course materials, this has minimal quality impact. For broad or interdisciplinary topics, retrieval quality may be slightly reduced.

**How to change:**
```yaml
rag:
  num_retrieval_results: 2   # changed from 5
```

---

## Recommended Presets

These presets show which keys to change together for common scenarios.

### Showcase / Demo mode

Optimized for live demonstrations or exploratory use where cost must be minimized and generation speed matters more than peak quality.

```yaml
llm:
  model_name: gpt-4o-mini

prefetch:
  enabled: false

skill_gap:
  max_goal_iterations: 1
  max_eval_iterations: 1

learning_plan:
  max_refinements: 0

content_generation:
  max_quality_rounds: 1
  max_knowledge_points: 2

chatbot:
  enable_media_search: false

rag:
  num_retrieval_results: 2
```

---

### Balanced mode

Moderate cost reduction while preserving the most impactful quality features. Recommended for ongoing learner use after the initial deployment period.

```yaml
llm:
  model_name: gpt-4o-mini

prefetch:
  enabled: false

content_generation:
  max_quality_rounds: 1
```

---

### Full quality (default)

No changes needed. All keys are at their default values as shipped.

---

## Access Control

To prevent new user registrations from triggering the full onboarding pipeline (skill gap analysis, learning path generation, content generation), the team recommends disabling the registration endpoint while keeping existing accounts active.

**How to disable registration:**

In `backend/main.py`, locate the `/auth/register` route and comment it out or add a `disabled` guard:

```python
# Disable registration to limit new pipeline runs
# @public_router.post("/auth/register", ...)
# async def register(...):
#     ...
```

Existing users can still log in and access their generated content. This prevents any new end-to-end pipeline runs triggered by onboarding.

---

## Notes

- **Audio narration (TTS):** Ami uses Microsoft Edge TTS for audio narration, which is a free service. Disabling audio has no effect on API costs.
- **Web search:** Ami uses DuckDuckGo for web search, which is also free. Disabling it saves no API spend but does reduce the breadth of content that can be referenced.
- **Bias audit:** The fairness audit that runs after skill gap analysis is not configurable — it always runs. It uses the lighter `gpt-4o-mini` model and has a low per-call cost.
- **Embeddings:** Ami uses `text-embedding-3-small` for all vector search operations. This model is very inexpensive ($0.02 per million tokens) and is not a meaningful cost driver.
