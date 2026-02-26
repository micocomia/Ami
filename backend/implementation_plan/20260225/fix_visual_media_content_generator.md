# Fix Visual Media in Content Generator (Backend)

## Context

Three bugs in the content generator's visual media pipeline were discovered and fixed in this sprint:

1. **Wikimedia images not retrieved** — the two-step flow (OpenSearch → REST Summary `thumbnail`) failed silently because many Wikipedia articles lack a `thumbnail` field. The result was that visual learners received no images.

2. **YouTube videos unrelated to session** — the query used only the knowledge point name with no course or session context, producing generic or off-topic results.

3. **Mermaid diagrams rendered as raw markdown** — the LLM outputs ` ```mermaid ``` ` blocks but Streamlit's `st.markdown()` has no Mermaid.js support, so diagrams appeared as raw code blocks.

Two additional improvements were layered on:
- An **LLM-based relevance filter** to remove off-topic resources even when queries return results.
- **Wikimedia Commons audio** as supplementary content for verbal learners, extending the existing TTS pipeline.

---

## Architecture

### Media Pipeline After Change

```
create_learning_content_with_llm()
    ↓
Determine max_videos, max_images, max_audio from fslsm_input
    → visual learner (≤ -0.3): max_videos + max_images
    → verbal learner (≥ +0.3): max_audio (Commons lectures/recordings)
    ↓
find_media_resources(search_runner, knowledge_points,
                     max_videos, max_images, max_audio,
                     session_context=session_title)
    → YouTube: site:youtube.com {topic} {session_title} tutorial
    → Wikimedia Commons images: file namespace, "diagram OR chart OR illustration"
    → Wikimedia Commons videos: file namespace, "video OR animation OR demonstration"
    → Wikimedia Commons audio:  file namespace, "lecture OR speech OR explanation"
    ↓
filter_media_resources_with_llm(llm, resources,
                                 session_title, kp_names)
    → MediaRelevanceEvaluator(BaseAgent) → one LLM call
    → returns boolean array; off-topic resources dropped
    ↓
integrate_learning_document_with_llm(..., media_resources=...)
    → prepare_markdown_document() renders section with adaptive header
```

### Diagram Pipeline After Change

```
draft_knowledge_point_with_llm()
    → drafter.draft(payload)         [LLM drafts content with mermaid blocks]
    → render_diagrams_in_markdown()  [POST each block to kroki.io/mermaid/svg]
    → SVG saved to data/diagrams/{uuid}.svg
    → code block replaced with ![Diagram](/static/diagrams/{uuid}.svg)
    ↓
main.py: /static/diagrams → StaticFiles(data/diagrams)
    ↓
Frontend absolutizes /static/diagrams/... to {backend_endpoint}/static/diagrams/...
    → st.markdown() renders as inline image
```

### Module Structure

```
modules/content_generator/
├── agents/
│   ├── media_resource_finder.py        ← rewritten (Commons replaces Wikipedia)
│   ├── media_relevance_evaluator.py    ← NEW (BaseAgent + helper function)
│   ├── diagram_renderer.py             ← NEW (Kroki SVG renderer)
│   ├── learning_content_creator.py     ← updated (session context, audio, filter)
│   ├── learning_document_integrator.py ← updated (audio type, adaptive header)
│   └── search_enhanced_knowledge_drafter.py ← updated (diagram post-processing)
├── prompts/
│   └── media_relevance_evaluator.py    ← NEW
└── schemas.py                          ← added MediaRelevanceResult
```

---

## Changes

### Fix 1: Wikimedia Commons Images — Replace Wikipedia 2-Step Flow

**`modules/content_generator/agents/media_resource_finder.py`** — complete rewrite of the image block.

**Old approach (removed):**
- Step 1: `en.wikipedia.org/w/api.php?action=opensearch` to resolve a canonical article title
- Step 2: `en.wikipedia.org/api/rest_v1/page/summary/{title}` to get `thumbnail.source`
- Problem: most articles lack `thumbnail` → silent zero-result failure; even when present, thumbnails are lead photos (portraits, flags) not educational diagrams

**New approach:**
- Single call to `commons.wikimedia.org/w/api.php` with `generator=search`, `gsrnamespace=6` (file namespace), `prop=imageinfo`, `iiprop=url|thumburl|extmetadata`
- Query augmented with `(diagram OR chart OR illustration)` to bias toward educational visuals
- Filters results by image file extensions (`{'.jpg', '.jpeg', '.png', '.svg', '.gif', '.tiff', '.tif', '.webp'}`) to exclude audio/video files that also appear in namespace 6
- Negative page IDs (missing results) guarded with `if int(page_id) < 0: continue`
- `extmetadata.ImageDescription` used as resource description; HTML tags stripped with `re.sub(r'<[^>]+>', '', ...)`
- File title cleaned: `"File:"` prefix and extension stripped, underscores replaced with spaces

### Fix 1b: Wikimedia Commons Videos — Secondary Video Source

**`modules/content_generator/agents/media_resource_finder.py`** — new Commons video search block appended after the YouTube loop.

- Searches `commons.wikimedia.org` file namespace for `.webm`, `.ogv`, `.ogg` files
- Query uses `(video OR animation OR demonstration)` to target educational motion content
- Only fills remaining `max_videos` slots not already filled by YouTube
- Adds `"source": "wikimedia_commons"` to distinguish from YouTube results
- Title used as `"snippet"` field for the relevance evaluator

### Fix 1c: Wikimedia Commons Audio — Verbal Learner Supplementary Resources

**`modules/content_generator/agents/media_resource_finder.py`** — new `max_audio` parameter (default `0`, backward-compatible) and audio search block.

- Searches Commons file namespace for `.ogg`, `.oga`, `.mp3`, `.flac`, `.wav` files
- Query uses `(lecture OR speech OR explanation OR audio)` to target academic recordings
- Stores `"audio_url"` (direct file URL for `<audio>` tag) and `"url"` (Commons page for attribution)

**`modules/content_generator/agents/learning_content_creator.py`** — extended media fetching:

```python
max_videos, max_images, max_audio = 0, 0, 0
if fslsm_input <= -_FSLSM_MODERATE:
    max_videos = 2 if fslsm_input <= -_FSLSM_STRONG else 1
    max_images = 2 if fslsm_input <= -_FSLSM_STRONG else 0
elif fslsm_input >= _FSLSM_MODERATE:
    max_audio = 2 if fslsm_input >= _FSLSM_STRONG else 1
```

Replaces the previous `if fslsm_input <= -_FSLSM_MODERATE:` guard that only handled visual learners.

**`modules/content_generator/agents/learning_document_integrator.py`** — audio type rendering:

```python
elif r_type == "audio":
    audio_url = resource.get("audio_url", "")
    url = resource.get("url", "")
    md += f"\n### 🔊 {r_title}\n"
    if audio_url:
        md += f'<audio controls src="{audio_url}"></audio>\n'
    if url:
        md += f"[View on Wikimedia Commons]({url})\n"
```

### Fix 2: YouTube Query — Add Session Context

**`modules/content_generator/agents/media_resource_finder.py`**

- New `session_context: str = ""` parameter added to `find_media_resources()`
- YouTube query: `f"site:youtube.com {topic}{context} tutorial"` (was `f"site:youtube.com {topic} tutorial education"`)
- `sr.snippet or ""` captured and stored as `"snippet"` in the result dict (used by the relevance evaluator without extra HTTP calls)
- `"source": "youtube"` added to result dicts

**`modules/content_generator/agents/learning_content_creator.py`**

- `session_title` extracted from `learning_session.get("title", "")` before media search
- Passed as `session_context=session_title` to `find_media_resources()`

### Fix 2b: LLM-Based Relevance Filter

**`modules/content_generator/prompts/media_relevance_evaluator.py`** — NEW

System prompt: instructs the evaluator to assess educational relevance against the session title and key topics. Handles VIDEO, IMAGE, and AUDIO types. Output format: `{"relevance": [true, false, ...]}`.

Task prompt: injects `{session_title}`, `{key_topics}`, and numbered `{resources}` list (type label + title + snippet/description truncated to 200 chars).

**`modules/content_generator/agents/media_relevance_evaluator.py`** — NEW

Follows the `BaseAgent` pattern established across all other agents:
- `MediaRelevanceEvaluator(BaseAgent)` — wraps `self.invoke()` and validates output against `MediaRelevanceResult`
- `filter_media_resources_with_llm()` — helper used by `learning_content_creator.py`; builds the numbered resource list, calls the evaluator, zips results with boolean judgments. Falls back to returning all candidates on any exception.

**`modules/content_generator/schemas.py`**

Added `MediaRelevanceResult`:
```python
class MediaRelevanceResult(BaseModel):
    relevance: List[bool]
```

**`modules/content_generator/agents/learning_content_creator.py`**

Lazy import (consistent with all sibling imports in this file):
```python
from .media_relevance_evaluator import filter_media_resources_with_llm
```

Called after `find_media_resources()` inside the `if _search_runner is not None` block, with its own internal `try/except` fallback — no outer guard needed.

### Fix 3: Mermaid Diagrams — Server-Side Rendering via Kroki API

**`modules/content_generator/agents/diagram_renderer.py`** — NEW

- Scans markdown for ` ```mermaid `, ` ```plantuml `, ` ```graphviz ` blocks using a compiled regex
- For each match: POST `code.encode("utf-8")` to `https://kroki.io/{type}/svg` with `Content-Type: text/plain`
- On success: writes SVG bytes to `data/diagrams/{uuid}.hex.svg`, returns `![Diagram](/static/diagrams/{filename})`
- On failure: returns original code block unchanged (graceful degradation)
- `DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)` called inside the function to ensure the directory exists on first call
- Fast-path early return when no diagram blocks are detected

**`modules/content_generator/agents/search_enhanced_knowledge_drafter.py`**

Post-processes each knowledge point draft inside `draft_knowledge_point_with_llm()` (runs in parallel via `ThreadPoolExecutor` in `draft_knowledge_points_with_llm()`):

```python
result = drafter.draft(payload)
try:
    from .diagram_renderer import render_diagrams_in_markdown
    if result.get("content"):
        result["content"] = render_diagrams_in_markdown(result["content"])
except Exception:
    pass
return result
```

**`main.py`**

```python
os.makedirs("data/diagrams", exist_ok=True)
app.mount("/static/diagrams", StaticFiles(directory="data/diagrams"), name="diagrams")
```

Mirrors the existing audio static mount pattern at line 45–46.

### Bug A: Adaptive Media Section Header

**`modules/content_generator/agents/learning_document_integrator.py`**

Old: hardcoded `"## 📺 Visual Learning Resources"` regardless of resource types.

New: derives header from actual resource types present:

```python
has_visual = any(r.get("type") in ("video", "image") for r in media_resources)
has_audio  = any(r.get("type") == "audio" for r in media_resources)
if has_visual and has_audio:
    section_label = "## 📚 Supplementary Learning Resources"
elif has_audio:
    section_label = "## 🔊 Audio Learning Resources"
else:
    section_label = "## 📺 Visual Learning Resources"
```

### Bug E: Outer Guards on Commons Loops

Commons video and audio loops are each wrapped in `if max_videos > 0:` / `if max_audio > 0:` respectively, consistent with the existing YouTube guard. The inner `break` conditions handle the count limit; the outer guard prevents any loop setup overhead when the count is already zero.

### Bug F: YouTube `source` and `snippet` Fields

The YouTube `results.append(...)` dict includes both `"snippet": sr.snippet or ""` and `"source": "youtube"`. This was required for the relevance evaluator (needs `snippet`) and the document renderer (uses `source` to determine the watch label).

---

## Design Decisions

**Why Wikimedia Commons over Wikipedia page thumbnails?**
Commons (`commons.wikimedia.org`) is the dedicated media repository for educational diagrams, illustrations, and SVGs. Wikipedia article thumbnails are lead photos (portraits, flags, or generic topic photos) — not educational visuals. The Commons file-namespace search (`gsrnamespace=6`) returns actual image files, and the "diagram OR chart OR illustration" bias ensures the results skew toward educational content.

**Why Kroki instead of client-side Mermaid.js?**
Streamlit's `st.markdown()` does not support Mermaid.js without a custom component or JavaScript injection. Server-side rendering via Kroki converts diagrams to static SVGs that render as ordinary `<img>` elements — no frontend changes to the Streamlit renderer or new npm packages needed. The approach also supports PlantUML and Graphviz at no additional cost.

**Why a single LLM call for all resources instead of per-resource calls?**
Batching all candidate resources into one `filter_media_resources_with_llm()` call (returning a boolean array) is cheaper and faster than N separate calls. The evaluator only needs title + snippet/description metadata — it does not visit URLs — so the batch is lightweight regardless of resource count.

**Why lazy import of `filter_media_resources_with_llm`?**
All sibling agent imports in `learning_content_creator.py` are lazy (inside the function body): `goal_oriented_knowledge_explorer`, `media_resource_finder`, `podcast_style_converter`, etc. A module-level import of `filter_media_resources_with_llm` would be inconsistent and could cause circular import issues at module load time.

**Why audio for verbal learners, not for visual learners?**
Visual learners already receive YouTube videos and Commons educational diagrams. Adding audio on top would dilute the signal. Verbal learners receive TTS-generated podcasts (`convert_to_podcast_with_llm` + `generate_tts_audio`). Commons audio (academic lectures, explanations) is complementary reference material for the same modality, not a duplicate.

**Why keep the `try/except Exception: media_resources = []` wrapper around `find_media_resources()`?**
`find_media_resources()` makes HTTP calls to external APIs (YouTube via search runner, Wikimedia Commons). Any network failure, timeout, or unexpected API response at the outer level (not caught by the individual `continue` handlers inside) must not crash content generation. The outer guard ensures `media_resources` is always a valid list.

---

## Known Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Kroki public API unavailable / rate limited | `try/except` in `replace_block()` keeps original mermaid block; content still usable |
| SVGs accumulate on disk | Same lifecycle as audio — transient per container restart |
| `data/diagrams/` missing on startup | `DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)` inside renderer + `os.makedirs` in `main.py` |
| Commons returns negative page IDs (no results) | `if int(page_id) < 0: continue` guard on every Commons loop |
| `.ogg` ambiguity (audio vs video) | Separate search queries bias results: "video OR animation" for video, "lecture OR speech" for audio |
| LLM filter over-aggressively removes valid resources | `filter_media_resources_with_llm()` falls back to returning all candidates on any exception |
| Long session title making YouTube query too broad | `except Exception: continue` handles zero-result queries; Commons fills remaining slots |
