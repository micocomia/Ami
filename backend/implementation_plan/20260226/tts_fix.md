## Tiered Automatic Audio Generation (Implement Option 2)

### Summary
Implement a two-tier adaptive audio policy based on `fslsm_input`:
- `>= 0.7` (strong auditory): keep current **host-expert** pipeline.
- `0.3 to <0.7` (moderate auditory): switch to cheaper **single-voice narration** directly from canonical lesson text (no podcast rewrite call).

This preserves automatic adaptation while reducing LLM cost for moderate auditory learners.

### Public Interface Changes
- `content_format` remains `audio_enhanced` for both moderate and strong auditory users.
- `audio_mode` semantics become:
  - `host_expert_optional` for strong auditory users.
  - `narration_optional` for moderate auditory users.
- `audio_url` behavior stays unchanged (present when TTS succeeds).

### Backend Changes

1. Update adaptive branch in [`learning_content_creator.py`](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/agents/learning_content_creator.py)
- Current behavior: all `fslsm_input >= 0.3` uses `convert_to_podcast_with_llm(..., mode="full")` then TTS.
- New behavior:
  - `fslsm_input >= 0.7`:
    - `audio_mode = "host_expert_optional"`
    - generate host-expert script via `convert_to_podcast_with_llm(..., mode="full")`
    - pass script to `generate_tts_audio`
  - `0.3 <= fslsm_input < 0.7`:
    - `audio_mode = "narration_optional"`
    - skip podcast conversion
    - pass `learning_document` directly to `generate_tts_audio`
- Keep existing graceful failure behavior (`audio_url` omitted on failure).

2. Mirror same logic in [`main.py`](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/main.py) `/integrate-learning-document`
- Keep endpoint response shape, but set `audio_mode` by tier exactly as above.
- Ensure moderate tier does not call podcast converter.

### Frontend Changes

1. Pass through `audio_mode` as-is (already present in request API adapter).
2. Update message text in [`knowledge_document.py`](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/pages/knowledge_document.py):
- If `content_format == "audio_enhanced"`:
  - `audio_mode == "host_expert_optional"`: keep current host-expert banner.
  - `audio_mode == "narration_optional"`: show narration-specific banner.
- Audio player logic remains based on `audio_url`.

### Tests

1. Update [`test_adaptive_content_delivery.py`](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/tests/test_adaptive_content_delivery.py):
- `test_moderate_audio`:
  - assert `content_format == "audio_enhanced"`
  - assert `audio_mode == "narration_optional"`
  - assert `convert_to_podcast_with_llm` **not called**
  - assert `generate_tts_audio` called once with integrated `learning_document`
- `test_strong_audio`:
  - keep host-expert assertions (`audio_mode == "host_expert_optional"`)
  - assert podcast converter called once

2. Add boundary tests:
- `fslsm_input == 0.3` routes to moderate narration tier.
- `fslsm_input == 0.7` routes to strong host-expert tier.

3. Endpoint-level check (for `/integrate-learning-document`):
- moderate request returns `audio_mode: narration_optional` and does not invoke converter.
- strong request returns `audio_mode: host_expert_optional` and invokes converter.

### Acceptance Criteria
- Moderate auditory lessons (`0.3 <= fslsm_input < 0.7`) no longer trigger `convert_to_podcast_with_llm`.
- Strong auditory lessons (`>= 0.7`) preserve current host-expert behavior.
- UI message matches `audio_mode`.
- Existing non-audio and visual branches remain unchanged.

### Assumptions / Defaults
- “Cheaper moderate mode” is implemented as **no LLM podcast rewrite** + direct TTS on canonical lesson markdown.
- No model-provider/model-size changes are introduced in this step.
- Current TTS function is reused without signature changes.
