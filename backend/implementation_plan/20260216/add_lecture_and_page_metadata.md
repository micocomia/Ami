# Plan: Add lecture_number and page_number metadata to verified content

## Context

The verified content indexing pipeline currently stores metadata like `course_code`, `course_name`, `term`, `content_category`, and `file_name` — but not **lecture number** or **page number**. Adding these enables future agents to handle requests like "I need help with Lecture 8 of Introduction to Python, pages 12-15" by filtering on structured metadata rather than relying on semantic search alone.

## Changes

### 1. Extract `lecture_number` from filenames (`verified_content_loader.py`)

Add a helper function that parses lecture numbers from filenames using regex. The three naming patterns in the repo are:

- `Lec_1.pdf` → 1
- `...MIT11_437F16_Lec3.pdf` → 3
- `...MIT6_831S11_lec01.pdf` → 1

Regex: `[Ll]ec_?(\d+)` — case-insensitive, optional underscore, captures digits.

- Add `_extract_lecture_number(file_name: str) -> Optional[int]` function
- Call it in `_load_and_tag()` and `load_course_documents()` where metadata is set, storing result as `lecture_number` (int or None)

### 2. Switch to DOC_CHUNKS export mode for page numbers (`verified_content_loader.py`)

Change `_load_with_docling()` to use `ExportType.DOC_CHUNKS` so Docling produces chunks with page metadata in `dl_meta`. Then extract `page_number` from the `dl_meta` JSON string and store it as a top-level int field.

- Import `ExportType` from `langchain_docling`
- Pass `export_type=ExportType.DOC_CHUNKS` to `DoclingLoader`
- After loading, parse `dl_meta` (JSON string) from each doc's metadata to extract page number info, and store as `doc.metadata["page_number"]` (int)
- Remove `dl_meta` from metadata after extraction (it's a complex JSON string that isn't useful to store raw)

### 3. Update metadata cleaning (`verified_content_manager.py`)

The existing metadata cleaning at lines 78-86 already keeps `int` values, so `lecture_number` (int) and `page_number` (int) will survive the filter. No changes needed to the filter logic itself, but verify `page_number` and `lecture_number` pass through.

### 4. Update tests (`tests/test_verified_content.py`)

- Add test for `_extract_lecture_number()` with various filename patterns
- Update `test_load_course_documents_has_metadata` to verify `lecture_number` is present in metadata for lecture files
- Add test that non-lecture files get `lecture_number: None`

### 5. Add "Verified Course Content" section to README (`README.md`)

Add a section after "RAG and Search Configuration" documenting:
- Directory structure: `{course_code}_{course-name}_{term}/`
- Subdirectories: `Syllabus/`, `Lectures/`, `Exercises/`, `References/`
- Recommended file naming: lecture files should contain `Lec_N` (e.g. `Lec_1.pdf`, `Lec_12.pdf`) so the system can extract lecture numbers
- Supported file types: `.pdf`, `.pptx`, `.json`, `.txt`, `.py`, `.md`
- Note that deleting `data/vectorstore/` forces re-indexing on next startup

## Files to modify

1. `base/verified_content_loader.py` — lecture number extraction, DOC_CHUNKS mode, page number extraction
2. `base/verified_content_manager.py` — no filter changes needed (verify only)
3. `tests/test_verified_content.py` — new tests for lecture_number
4. `README.md` — add verified content documentation section

## Verification

1. Run `pytest tests/test_verified_content.py -v` to verify all tests pass
2. Delete `data/vectorstore/` directory to force re-indexing
3. Start the server and check logs for successful indexing with new metadata
