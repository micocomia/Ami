# Frontend Implementation Plan: Verified Content Source Attribution

**Date:** 2026-02-15
**Branch:** sprint-2

## Context

The backend is being enhanced to use verified course content as the primary RAG source. The frontend needs to display source attribution so learners know whether content comes from curated university materials or web search.

## Files to Modify

### 1. `frontend/pages/knowledge_document.py` — Source Attribution Banner

**In `render_content_preparation()`** (around line 217, after Stage 2):
- After `draft_knowledge_points()` returns, extract `sources_used` from the drafts.
- Store `sources_used` in the session cache alongside the document.

**In `render_learning_content()`** (around line 48, before document rendering):
- Read `sources_used` from cached learning content.
- Display `st.info()` banner:
  - Verified only: `"Content sourced from verified university course materials (MIT OpenCourseWare)"`
  - Web only: `"Content supplemented with web search results"`
  - Both: `"Content sourced from verified course materials, supplemented with web search"`

### 2. `frontend/utils/format.py` — Source Type Extraction Helper

Add `extract_sources_used(knowledge_drafts)`:
- Iterates over all knowledge drafts.
- Collects unique `sources_used` values across all drafts.
- Returns deduplicated list like `["verified_content", "web_search"]`.

## Verification

1. Set a goal matching verified content (e.g., "Introduction to Computer Science and Programming in Python") → banner shows "verified university course materials"
2. Set a goal NOT in verified content (e.g., "Learn Kubernetes") → banner shows "web search results"
