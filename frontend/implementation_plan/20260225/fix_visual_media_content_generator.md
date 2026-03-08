# Fix Visual Media in Content Generator (Frontend)

## Context

The backend content generator now produces:
- Wikimedia Commons educational images (diagrams, charts, illustrations)
- Wikimedia Commons audio resources for verbal learners with `<audio controls src="...">` HTML tags
- Mermaid/PlantUML/Graphviz diagrams rendered to SVG by Kroki and served at `/static/diagrams/{uuid}.svg`

Without a frontend change, all three would fail to display:
- The diagram image paths `/static/diagrams/...` are **relative to the backend**, not to Streamlit's origin. `st.markdown()` would request them from the Streamlit server (port 8501), which has no such route.
- The same issue applies to any other `/static/` backend path embedded in markdown (e.g., future audio references).

---

## Change

### `frontend/pages/knowledge_document.py`

**Import extension** (line 13) — `backend_endpoint` added to the existing `config` import:

```python
# Before
from config import use_mock_data, use_search

# After
from config import use_mock_data, use_search, backend_endpoint
```

`backend_endpoint` is already defined in `frontend/config.py`:
```python
backend_endpoint = os.getenv("BACKEND_ENDPOINT", "http://127.0.0.1:8000/")
```

No new import, no new module dependency.

---

**URL absolutization** in `render_document_content_by_section()` — inserted between `inject_citation_tooltips` and `st.markdown`:

```python
# Before
section_md = section_documents[current_page]
if sources_used:
    section_md = inject_citation_tooltips(section_md, sources_used)
st.markdown(section_md, unsafe_allow_html=True)

# After
section_md = section_documents[current_page]
if sources_used:
    section_md = inject_citation_tooltips(section_md, sources_used)
# Absolutize backend static URLs (diagrams, audio) for the Streamlit renderer
_backend_base = backend_endpoint.rstrip('/')
section_md = section_md.replace('/static/', f'{_backend_base}/static/')
st.markdown(section_md, unsafe_allow_html=True)
```

This replaces every occurrence of `/static/` with `{backend_endpoint}/static/` (e.g., `http://127.0.0.1:8000/static/`) before the markdown is handed to Streamlit, so:
- `![Diagram](/static/diagrams/abc123.svg)` → `![Diagram](http://127.0.0.1:8000/static/diagrams/abc123.svg)` — renders as an inline image
- `<audio controls src="/static/audio/...">` → fully qualified URL — plays correctly in the browser
- All other markdown content is unaffected (no `/static/` occurrences in normal text)

---

## Design Decisions

**Why string replace over a custom markdown parser?**
The markdown returned by the backend is already well-structured. The only paths that need rewriting are those starting with `/static/`, which is a narrow, non-ambiguous pattern. A regex or AST-based approach would be heavier with no additional correctness benefit for this use case.

**Why `backend_endpoint.rstrip('/')` instead of `st.session_state["backend_endpoint"]`?**
The session state key `"backend_endpoint"` is set elsewhere in the app for dynamic endpoint switching, but `config.backend_endpoint` is the authoritative default used by all other API calls in this file (via `request_api.py`). Using the config value directly is consistent with the rest of `knowledge_document.py`.

**Why only fix `render_document_content_by_section` and not `render_document_content_by_document`?**
The application routes all session document rendering through `render_document_content_by_section` (see `render_type = "by_section"` at line 58). `render_document_content_by_document` is the legacy fallback path and is not exercised in the current UI. Applying the fix only to the active path minimizes the change footprint.

**Why not use `unsafe_allow_html=True` for audio specifically?**
`st.markdown(..., unsafe_allow_html=True)` was already set before this change — it is required for the citation tooltips rendered by `inject_citation_tooltips()`. No new `unsafe_allow_html` exposure is introduced.

---

## Files Modified

| File | Change |
|------|--------|
| `frontend/pages/knowledge_document.py` | Extended `from config import ...` to include `backend_endpoint`; added `/static/` URL absolutization in `render_document_content_by_section()` before `st.markdown()` |
