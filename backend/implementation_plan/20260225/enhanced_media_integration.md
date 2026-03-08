### FSLSM Granular Allowances with Verbal Equivalents (Stories/Poems) + Optional Host-Expert Listen Mode

### Summary
Implement a unified adaptation policy where each FSLSM tier gets independent allowances for:
- `videos`
- `images`
- `diagrams` (visual equivalent)
- `audio`
- `narratives` (verbal equivalent: short stories or poems)

Lessons remain text-first. For verbal learners, add:
1. Inline narrative inserts (story/poem) as diagram-equivalent supports.
2. Optional host-expert audio mode emphasizing key points.

---

### Decision-Complete Behavior

1. Allowance matrix (locked)
- Strong visual (`fslsm_input <= -0.7`):
  - `videos=3, images=3, diagrams=3, audio=0, narratives=0`, `video_focus="visual"`
- Moderate visual (`-0.7 < x <= -0.3`):
  - `videos=1, images=1, diagrams=1, audio=0, narratives=0`, `video_focus="visual"`
- Neutral (`-0.3 < x < 0.3`):
  - all `0`
- Moderate verbal (`0.3 <= x < 0.7`):
  - `audio=1, videos=1, diagrams=0, images=0, narratives=1`, `video_focus="audio"`
- Strong verbal (`x >= 0.7`):
  - `audio=3, videos=3, diagrams=0, images=0, narratives=3`, `video_focus="audio"`

2. Narrative allowance model (locked)
- Shared narrative pool (`narratives`) where each unit is either:
  - `short_story` or
  - `poem`
- Type chosen per section/topic fit by LLM, up to cap.

3. Narrative placement (locked)
- Inline near relevant section headings (not only appendix).
- At most one narrative insert per section unless cap exceeds section count.

4. Narrative audio mode (locked)
- Narrative text always visible.
- Each narrative may optionally include a small TTS audio clip (per-item audio URL), independent of host-expert audio.
- Host-expert audio remains a separate optional companion for verbal learners.

---

### Implementation Changes

1. New policy helper
- Add `get_adaptation_allowances(fslsm_input)` shared by:
  - [backend/main.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/main.py)
  - [backend/modules/content_generator/agents/learning_content_creator.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/agents/learning_content_creator.py)
- Returns all caps + `video_focus`.

2. Media finder extension
- In [media_resource_finder.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/agents/media_resource_finder.py):
  - Add `video_focus` param to bias verbal-video queries toward lecture/explanation/talk style.

3. Narrative generator (new agent)
- Add `narrative_resource_generator.py` + prompt file.
- Input: section text/title, learner profile, narrative cap remaining.
- Output schema per item:
  - `type`: `short_story | poem`
  - `title`
  - `content`
  - `section_anchor`
  - optional `audio_url`
- Generate items only for verbal tiers.

4. Integrator updates
- In [learning_document_integrator.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/agents/learning_document_integrator.py):
  - Accept optional `narrative_resources`.
  - Inject narratives inline beneath matched `##`/`###` sections.
  - Render optional per-item audio players when present.

5. Diagram cap enforcement
- Keep diagram source as generated diagrams (renderer output).
- Add count/trim helper in [diagram_renderer.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/agents/diagram_renderer.py) or companion util.
- Enforce cap post-render.

6. Verbal mode content strategy
- Do not overwrite lesson into podcast format.
- Keep written lesson as canonical `learning_document`.
- Add optional host-expert audio companion:
  - produce host-expert script separately
  - generate `audio_url` from that script for verbal tiers.

7. Frontend wiring
- In [frontend/utils/request_api.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/utils/request_api.py), pass through new optional fields.
- In [frontend/pages/knowledge_document.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/pages/knowledge_document.py):
  - Keep current document rendering.
  - Show optional “Listen to host-expert emphasis” player.
  - Inline narrative blocks already arrive inside markdown; optional narrative audio tags render naturally.

---

### Public Interface / Schema Changes

1. Backend response additions for integrate endpoint
- Keep existing:
  - `learning_document`, `content_format`, `audio_url`, `document_is_markdown`
- Add optional:
  - `audio_mode`: `"host_expert_optional"` for verbal tiers
  - `narrative_resources_count`: int (debug/telemetry-friendly)
- `content_format` values become:
  - `standard`, `visual_enhanced`, `audio_enhanced`

2. Internal schemas
- Add `NarrativeResource` pydantic model in content generator schemas.

---

### Tests and Acceptance Criteria

1. Policy tests
- Boundary tests at `-0.7, -0.3, 0.3, 0.7` for all caps.

2. Narrative generation tests
- Verbal moderate/strong generate <= cap.
- Returned type is only `short_story` or `poem`.
- Narrative inserts are section-anchored and inline.

3. Diagram cap tests
- Ensure rendered diagram count never exceeds allowance.

4. Endpoint integration tests
- Visual strong: 3/3/3 media behavior.
- Verbal strong: audio/video caps + narratives=3 + text preserved.
- Neutral: no media/narratives.

5. Regression tests
- `learning_document` remains readable markdown.
- Frontend still renders sections/quizzes and optional audio without breakage.

---

### Assumptions
- Narrative inserts are pedagogical supplements, not replacements of core explanations.
- Per-narrative TTS is best-effort; failures do not block lesson generation.
- Host-expert audio is optional and always supplementary to the written lesson.
