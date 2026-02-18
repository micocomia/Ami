# Backend Implementation Plan: Verified Content RAG

**Date:** 2026-02-15
**Branch:** sprint-2

## Context

The current RAG pipeline (`SearchRagManager` in `base/search_rag.py`) only uses web search (DuckDuckGo) to find external resources when drafting knowledge content. The `data/verified-course-content/` folder contains curated university course materials (PDFs, PPTX, JSON). The goal is to make these verified materials the **primary** source, using web search only as a fallback.

## Strategy

Dual-collection Chroma architecture with verified-first retrieval. Use `DoclingLoader` for local files (layout-aware, OCR), keep `WebBaseLoader` for web search (fast, sufficient for HTML).

## Files Created

### 1. `base/verified_content_loader.py` — Document Loader for Local Files

Scans `data/verified-course-content/` and loads files into LangChain `Document` objects.

- **`scan_courses(base_dir)`** — Iterates course folders (pattern: `{code}_{name}_{term}`), returns list of course metadata dicts.
- **`load_course_documents(course_dir, course_metadata)`** — Loads files from Syllabus/, Lectures/, Exercises/, References/ subdirectories.
- **`load_file(file_path)`** — Dispatches based on extension:
  - `.json` → Parse JSON, extract `content` field, return as `Document`
  - `.pdf`, `.pptx` → Use `DoclingLoader` from `langchain_docling`
  - `.py` / other text → Read as plain text `Document`
- **Metadata** on every document: `source_type="verified_content"`, `course_code`, `course_name`, `term`, `content_category`, `file_name`
- **`load_all_verified_content(base_dir)`** — Top-level function returning flat list of `Document` objects.

### 2. `base/verified_content_manager.py` — Verified Content Index Manager

- **`VerifiedContentManager`** class:
  - `__init__(embedder, text_splitter, persist_directory, collection_name="verified_content")`
  - `index_verified_content(base_dir)` — Loads, splits, and adds to vectorstore. Skips if collection already has documents.
  - `retrieve(query, k=5)` → `List[Document]`
  - `list_courses()` → List of course metadata dicts.
  - `from_config(config)` — Static factory.

### 3. `tests/test_verified_content.py` — Test Script

**`TestVerifiedContentLoader`** (6 tests):
- `test_scan_courses_finds_all_courses` — 3 courses with correct metadata
- `test_scan_courses_empty_dir` — Empty dir returns empty list
- `test_load_file_json` — JSON syllabus loads correctly
- `test_load_file_text` — `.py` file reads as plain text
- `test_load_file_unsupported_skipped` — `.DS_Store`/`.keep` skipped
- `test_load_course_documents_has_metadata` — All metadata fields present

**`TestVerifiedContentManager`** (5 tests):
- `test_from_config_creates_manager`
- `test_index_and_retrieve` — Index docs, retrieve by query, verify `source_type` metadata
- `test_index_skips_if_already_indexed` — No duplicate indexing
- `test_retrieve_empty_collection` — Returns empty list
- `test_list_courses`

**`TestHybridRetrieval`** (4 tests):
- `test_invoke_hybrid_verified_only` — Verified >= k results, web search NOT called
- `test_invoke_hybrid_falls_back_to_web` — Verified < k, web called, verified docs first
- `test_invoke_hybrid_no_verified_manager` — Falls back to web entirely
- `test_invoke_hybrid_source_types_preserved`

## Files Modified

### 4. `config/default.yaml` — Added Verified Content Config

```yaml
verified_content:
  base_dir: data/verified-course-content
  collection_name: verified_content
  enabled: true
```

### 5. `base/search_rag.py` — Added Hybrid Retrieval

- Added `verified_content_manager: Optional[VerifiedContentManager]` to `__init__` and `from_config`.
- New method **`invoke_hybrid(query, k=5)`**:
  1. Retrieve from verified content: `verified_docs = self.verified_content_manager.retrieve(query, k=k)`
  2. If `len(verified_docs) >= k`: return verified docs only.
  3. Otherwise: run web search (`self.invoke(query)`), combine results (verified first, web fills remaining).
- `invoke()` unchanged for backward compatibility.
- `from_config()` instantiates `VerifiedContentManager` when `verified_content.enabled` is true.

### 6. `modules/content_generator/agents/search_enhanced_knowledge_drafter.py` — Uses Hybrid Retrieval

- Replaced `self.search_rag_manager.invoke(query)` → `self.search_rag_manager.invoke_hybrid(query)`
- After retrieving docs, collects unique `source_type` values and includes as `sources_used` in the returned draft.

### 7. `modules/content_generator/schemas.py` — Added Sources Field

- Added `sources_used: Optional[List[str]] = None` to `KnowledgeDraft` schema.

### 8. `main.py` — Indexes Verified Content on Startup

In `_load_stores()`:
```python
if search_rag_manager.verified_content_manager:
    search_rag_manager.verified_content_manager.index_verified_content(
        app_config.get("verified_content", {}).get("base_dir", "data/verified-course-content")
    )
```

## Verification

1. `python -m pytest backend/tests/test_verified_content.py -v` — all 15 tests pass
2. Start app, check logs for verified content indexing (Chroma collection count)
3. `python -m pytest backend/tests/ -v` — no regressions

## Key Design Decisions

1. **DoclingLoader for verified content, WebBaseLoader for web** — Layout-aware parsing for local files, fast HTML scraping for web.
2. **Separate Chroma collection** — `verified_content` vs `genmentor`. Prevents web noise from diluting verified materials.
3. **Verified-first retrieval** — Always try verified content first; web search only when insufficient.
4. **Source provenance preserved** — `source_type` metadata flows from vectorstore → `format_docs()` → LLM prompt → `KnowledgeDraft.sources_used` → frontend banner.
5. **Startup indexing with dedup** — Index once at startup, skip if already populated.
6. **No new dependencies** — Everything already in `requirements.txt`.
