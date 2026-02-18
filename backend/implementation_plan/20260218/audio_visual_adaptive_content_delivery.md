# Implementation Plan: Audio-Visual Adaptive Content Delivery

**Date**: 2026-02-18
**Sprint**: 3 — Agentic Content Generator
**Branch**: `sprint-3-agentic-content-generator`

---

## Overview

Extends the content generator pipeline to deliver adaptive learning content based on the learner's `fslsm_input` sensory modality dimension (range -1 to 1):

| `fslsm_input` | Mode | Behaviour |
|---|---|---|
| ≤ -0.7 | Strong visual | Mermaid diagrams + tables in draft; 2 YouTube videos + 2 Wikipedia images appended |
| -0.7 to -0.3 | Moderate visual | Tables/diagrams via hints; 1 YouTube video |
| -0.3 to +0.3 | Standard | No change |
| +0.3 to +0.7 | Moderate auditory | Full document rewritten as rich verbal narrative with analogies |
| ≥ +0.7 | Strong auditory | Host-Expert dialogue rewrite + dual-voice EdgeTTS MP3 |

Thresholds: `STRONG = 0.7`, `MODERATE = 0.3`

---

## Modified Pipeline (`create_learning_content_with_llm`, genmentor branch)

```
1. explore_knowledge_points_with_llm()
2. _get_fslsm_input() + _visual_formatting_hints()
3. draft_knowledge_points_with_llm(..., visual_formatting_hints=hints)
4. [fslsm_input ≤ -0.3] find_media_resources() → media_resources list
5. integrate_learning_document_with_llm(..., media_resources=media_resources)
   → prepare_markdown_document() appends ## 📺 Visual Learning Resources if media present
6. [fslsm_input ≥ +0.3] convert_to_podcast_with_llm()
   → mode="rich_text" (+0.3 to +0.7): narrative rewrite
   → mode="full" (≥+0.7): Host-Expert dialogue
7. [fslsm_input ≥ +0.7] generate_tts_audio() → MP3 → audio_url
   → Prepend <audio controls src="..."> tag to document
8. generate_document_quizzes_with_llm()
```

Response gains new fields:
- `content_format`: `"standard"` | `"visual_enhanced"` | `"podcast"`
- `audio_url`: present only when TTS succeeds for strong auditory learners

---

## Files Created

### `backend/modules/content_generator/prompts/podcast_style_converter.py`
System prompts for the two podcast conversion modes:
- `FULL_SYSTEM_PROMPT` — Host-Expert dialogue with alternating `**[HOST]**:`/`**[EXPERT]**:` turns, `# 🎧 [Podcast]` title prefix, `##` topic headings
- `RICH_TEXT_SYSTEM_PROMPT` — Continuous first-person narrative with analogies and vivid metaphors; same structure as original
- `TASK_PROMPT` — Takes `{document}` and `{learner_profile}` placeholders

### `backend/modules/content_generator/agents/media_resource_finder.py`
`find_media_resources(search_runner, knowledge_points, max_videos=2, max_images=2) -> List[dict]`

- **YouTube**: searches `"site:youtube.com {topic} tutorial education"` via `SearchRunner.invoke()`, extracts 11-char video IDs via regex, deduplicates, builds thumbnail URLs from `img.youtube.com/vi/ID/mqdefault.jpg`
- **Wikipedia**: calls OpenSearch API then REST Summary API for each topic; extracts `thumbnail.source`, `description`, `content_urls.desktop.page`
- All HTTP via `requests.get(timeout=5)`; any exception silently skipped

### `backend/modules/content_generator/agents/podcast_style_converter.py`
`PodcastStyleConverter(BaseAgent)` with `mode="full"` or `mode="rich_text"`.
`convert_to_podcast_with_llm(llm, document, learner_profile, mode) -> str`

### `backend/modules/content_generator/agents/tts_generator.py`
`generate_tts_audio(document) -> str` — dual-voice EdgeTTS MP3 generation:
- `_strip_markdown()` — cleans bold, headings, links, HTML tags
- `_parse_dialogue_turns()` — extracts `(SPEAKER, text)` pairs using regex `\*\*\[(\w+)\]\*\*:[ \t]*(.*?)(?=\n\*\*\[|\Z)` with DOTALL; key fix: `[ \t]*` instead of `\s*` to preserve newline for lookahead
- Dual voices: `en-US-JennyNeural` (HOST) and `en-US-GuyNeural` (EXPERT) shuffled randomly
- Per-turn MP3s generated via `edge_tts.Communicate` in a temp dir, concatenated and saved to `data/audio/`
- Returns `/static/audio/<uuid>.mp3`

### `backend/tests/test_adaptive_content_delivery.py`
29 unit tests across 6 test classes. All pass with no LLM or network calls.

---

## Files Modified

### `backend/modules/content_generator/schemas.py`
Added `MediaResource(BaseModel)` with fields: `type`, `title`, `url`, `video_id=""`, `thumbnail_url=""`, `image_url=""`, `description=""`

### `backend/modules/content_generator/prompts/search_enhanced_knowledge_drafter.py`
Appended `{visual_formatting_hints}` at the end of `search_enhanced_knowledge_drafter_task_prompt`

### `backend/modules/content_generator/agents/search_enhanced_knowledge_drafter.py`
- Added `visual_formatting_hints: str = ""` to `KnowledgeDraftPayload`
- Added `visual_formatting_hints: str = ""` parameter to `draft_knowledge_point_with_llm()` and `draft_knowledge_points_with_llm()`, threaded through to payload and closure

### `backend/modules/content_generator/agents/learning_document_integrator.py`
- Added `Optional[List[dict]]` import
- Added `media_resources: Optional[List[dict]] = None` to `integrate_learning_document_with_llm()` and `prepare_markdown_document()`
- `prepare_markdown_document()` appends `## 📺 Visual Learning Resources` section with video thumbnails and Wikipedia image links when `media_resources` is non-empty

### `backend/modules/content_generator/agents/learning_content_creator.py`
Added module-level constants and helpers:
- `_FSLSM_STRONG = 0.7`, `_FSLSM_MODERATE = 0.3`
- `_get_fslsm_input(learner_profile) -> float` — safely extracts nested value, handles string/dict/missing
- `_visual_formatting_hints(fslsm_input) -> str` — returns Mermaid/table instruction string for visual learners

Modified `create_learning_content_with_llm()` genmentor branch to implement the 8-step adaptive pipeline above.

### `backend/modules/content_generator/agents/__init__.py`
Added exports: `find_media_resources`, `PodcastStyleConverter`, `convert_to_podcast_with_llm`, `generate_tts_audio`

### `backend/main.py`
Mounts static audio directory after `app = FastAPI()`:
```python
from fastapi.staticfiles import StaticFiles
import os
os.makedirs("data/audio", exist_ok=True)
app.mount("/static/audio", StaticFiles(directory="data/audio"), name="audio")
```

### `backend/requirements.txt`
Added `edge-tts` (free Microsoft Edge cloud TTS, no API key required)

---

## Design Decisions

1. **`[ \t]*` vs `\s*` in dialogue parser**: Using horizontal-whitespace-only match so the newline before the next `**[SPEAKER]**:` label is preserved for the lookahead to work correctly. `\s*` greedily consumed newlines, breaking turn boundary detection.

2. **Graceful TTS failure**: If `generate_tts_audio()` raises (e.g., network issue, `edge-tts` not installed), the podcast text document is returned without `audio_url`. No server crash.

3. **Search runner sourcing**: In `create_learning_content_with_llm()`, the media finder tries `search_rag_manager.search_runner` first (zero-cost reuse), then falls back to `SearchRunner.from_config(default_config)`, then silently skips if unavailable.

4. **MP3 concatenation**: Raw byte concatenation of per-turn MP3 files works in modern browsers. `pydub`/`ffmpeg` can be swapped in for gapless output without signature changes.

5. **Backward compatibility**: All new parameters (`visual_formatting_hints`, `media_resources`) have defaults, so existing API callers are unaffected.

---

## Verification

| Scenario | `fslsm_input` | Expected |
|---|---|---|
| Strong visual | -0.9 | Draft has Mermaid + tables; doc ends with `📺` section (2 videos + 2 images); `content_format == "visual_enhanced"` |
| Moderate visual | -0.5 | Tables/diagrams via hints; 1 video; `content_format == "visual_enhanced"` |
| Standard | 0.0 | Unmodified document; `content_format == "standard"` |
| Moderate audio | +0.5 | Rich narrative with analogies; `content_format == "podcast"`; no `audio_url` |
| Strong audio | +0.9 | Host-Expert dialogue; dual-voice MP3; `content_format == "podcast"`; `audio_url` present; `<audio>` tag at top |
| TTS failure | +0.9 | Podcast text intact; no `audio_url`; no crash |

**Unit tests**: `pytest backend/tests/test_adaptive_content_delivery.py -v` → **29 passed**
