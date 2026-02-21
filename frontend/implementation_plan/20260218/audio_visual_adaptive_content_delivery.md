# Audio-Visual Adaptive Content Delivery — Frontend

**Date**: 2026-02-18
**Sprint**: 3 — Agentic Content Generator
**Branch**: `sprint-3-agentic-content-generator`

---

## Context

The backend now adapts the content format of every session document based on the learner's `fslsm_input` sensory modality score:

| `fslsm_input` | `content_format` | Behaviour |
|---|---|---|
| ≤ -0.7 | `visual_enhanced` | Mermaid diagrams + tables; 2 YouTube videos + 2 Wikipedia images appended as `## 📺 Visual Learning Resources` |
| -0.7 to -0.3 | `visual_enhanced` | Tables/diagrams via drafting hints; 1 YouTube video |
| -0.3 to +0.3 | `standard` | No change |
| +0.3 to +0.7 | `podcast` | Full document rewritten as rich first-person narrative |
| ≥ +0.7 | `podcast` | Host-Expert dialogue + dual-voice EdgeTTS MP3; `<audio controls>` tag prepended to document |

The `/integrate-learning-document` endpoint response now carries two new fields:
- `content_format`: `"standard"` | `"visual_enhanced"` | `"podcast"`
- `audio_url`: relative path `/static/audio/<uuid>.mp3` (only when TTS succeeds)

Before this plan the frontend silently discarded both fields.

**Depends on:** `backend/implementation_plan/20260218/audio_visual_adaptive_content_delivery.md`

---

## 1. API Layer — `integrate_learning_document()` Return Type

**File:** `frontend/utils/request_api.py`

### 1A. Previous behaviour

```python
response = make_post_request("integrate-learning-document", data, ...)
if output_markdown:
    return response.get("learning_document") if response else None
else:
    return response.get("learning_document") if response else None
```

Both branches returned only the `learning_document` string, discarding any extra fields.

### 1B. New behaviour

```python
response = make_post_request("integrate-learning-document", data, ...)
if not response:
    return None
# Return enriched dict including audio-visual metadata from Sprint 3 backend
return {
    "learning_document": response.get("learning_document"),
    "content_format": response.get("content_format", "standard"),
    "audio_url": response.get("audio_url"),
}
```

The return type changed from `str | None` to `dict | None`. All callers must be updated accordingly (see §2B).

---

## 2. Knowledge Document Page Updates

**File:** `frontend/pages/knowledge_document.py`

### 2A. Import

`get_quiz_mix` was added to the import in this sprint but is unrelated to audio-visual delivery. No additional imports are needed for this feature.

### 2B. `render_content_preparation()` — unpack enriched response

`integrate_learning_document` previously assigned its result to `document_structure` directly. After the return-type change the caller must extract the document string separately:

```python
# Before:
document_structure = integrate_learning_document(...)
learning_document = prepare_markdown_document(document_structure, ...)

# After:
integration_result = integrate_learning_document(...)
if integration_result is None:
    st.error("Failed to integrate knowledge document.")
    return
document_structure = integration_result["learning_document"]
content_format     = integration_result.get("content_format", "standard")
audio_url          = integration_result.get("audio_url")
learning_document  = prepare_markdown_document(document_structure, ...)
```

Both `content_format` and `audio_url` are stored in the document cache:

```python
learning_content = {
    "document": learning_document,
    "sources_used": sources_used,
    "content_format": content_format,   # NEW
    "audio_url": audio_url,             # NEW
}
```

Storing them in the cache means the values survive Streamlit reruns and are available every time the user visits the page without re-generating the document.

### 2C. `render_learning_content()` — format badge and audio player

After loading the cached content (the `else` branch), read the new fields and surface them to the user before rendering the first document section:

```python
content_format = learning_content.get("content_format", "standard")
audio_url      = learning_content.get("audio_url")

if content_format == "podcast":
    st.info("🎙️ This content has been adapted into a podcast-style format for auditory learners.")
    if audio_url:
        full_audio_url = (
            audio_url if audio_url.startswith("http")
            else f"{__import__('config').backend_endpoint.rstrip('/')}{audio_url}"
        )
        st.audio(full_audio_url, format="audio/mp3")
elif content_format == "visual_enhanced":
    st.info("📊 This content includes visual resources (diagrams, videos, images) for visual learners.")
```

**Design decisions:**

- `st.audio()` uses Streamlit's native audio widget which streams from a URL — no client-side file management needed.
- `audio_url` from the backend is a relative path (`/static/audio/<uuid>.mp3`). The full URL is constructed by stripping the trailing slash from `backend_endpoint` and concatenating. If the backend ever returns an absolute URL the `startswith("http")` guard handles that transparently.
- The banner is shown once, above the paginated document viewer, so the user sees it on every page of the document without it being buried in section 3.
- The `standard` format produces no banner — existing behaviour is preserved.

### 2D. Podcast document rendering (transparent)

For `podcast` content, the document text is already a Host-Expert dialogue (the backend rewrites it). The existing `st.markdown(..., unsafe_allow_html=True)` call renders `**[HOST]**:` and `**[EXPERT]**:` turns as bold text. No additional rendering logic is needed.

For `visual_enhanced` content, the `## 📺 Visual Learning Resources` section appended by the backend appears as a normal `##`-level section in the paginated TOC sidebar, with YouTube thumbnail links and Wikipedia image links rendered as standard markdown. No additional rendering logic is needed.

The `<audio controls src="...">` HTML tag that the backend prepends to the document for strong auditory learners is rendered correctly by `unsafe_allow_html=True`. The standalone `st.audio()` widget above the document provides a more discoverable alternative.

---

## Implementation Order

| Step | What | File | Notes |
|------|------|------|-------|
| 1 | Update `integrate_learning_document()` return type | `utils/request_api.py` | Changes str → dict |
| 2 | Unpack enriched response in `render_content_preparation()` | `pages/knowledge_document.py` | Must follow Step 1 |
| 3 | Store `content_format` and `audio_url` in document cache | `pages/knowledge_document.py` | Part of Step 2 |
| 4 | Render format badge + audio player in `render_learning_content()` | `pages/knowledge_document.py` | Reads from cache set in Step 3 |
| 5 | Update user flows test plan | `docs/user_flows_test_plan.md` | Flow 11 added |

---

## Verification

1. **Strong visual learner**: Select "Visual Learner" persona, generate session content. Verify info banner: "📊 This content includes visual resources…". Scroll through document sections — confirm `## 📺 Visual Learning Resources` section with YouTube and Wikipedia links appears.
2. **Standard learner**: Select "Balanced Learner" persona. Verify no banner is shown. Document format unchanged.
3. **Moderate auditory learner** (fslsm_input ≈ +0.5): Generate session content. Verify banner: "🎙️ This content has been adapted into a podcast-style format…". No audio player (TTS not triggered). Document is rich narrative prose.
4. **Strong auditory learner** (fslsm_input ≥ +0.7): Generate session content. Verify banner + `st.audio()` player. Click play — audio streams from backend. Document shows `**[HOST]**:` / `**[EXPERT]**:` dialogue.
5. **TTS failure fallback**: When backend cannot generate MP3, `audio_url` is absent. Verify banner still appears, audio player absent, no UI crash.
6. **Cache persistence**: Load the page a second time without regenerating. Verify banner and audio player are still shown (values restored from `document_caches`).
7. **Backward compatibility**: Load a session cached before Sprint 3 (no `content_format` key). Verify `get("content_format", "standard")` defaults to no banner. No errors.
