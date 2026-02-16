import os
import re
import json
import logging
import warnings
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".json", ".pdf", ".pptx", ".py", ".txt", ".md"}
SKIP_FILES = {".DS_Store", ".keep", ".keep 2", ".gitkeep", "Thumbs.db"}
CONTENT_CATEGORIES = {"Syllabus", "Lectures", "Exercises", "References"}

_LECTURE_NUMBER_RE = re.compile(r"[Ll]ec_?(\d+)")


def _extract_lecture_number(file_name: str) -> Optional[int]:
    """Extract lecture number from filename patterns like Lec_1.pdf, MIT11_437F16_Lec3.pdf, MIT6_831S11_lec01.pdf."""
    match = _LECTURE_NUMBER_RE.search(file_name)
    if match:
        return int(match.group(1))
    return None


def scan_courses(base_dir: str) -> List[Dict[str, Any]]:
    """Iterates course folders (pattern: {code}_{name}_{term}), returns list of course metadata dicts."""
    courses = []
    if not os.path.isdir(base_dir):
        logger.warning(f"Verified content directory does not exist: {base_dir}")
        return courses

    for entry in sorted(os.listdir(base_dir)):
        entry_path = os.path.join(base_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        if entry.startswith("."):
            continue

        parts = entry.split("_", 2)
        if len(parts) >= 3:
            course_code = parts[0]
            course_name = parts[1].replace("-", " ")
            term = parts[2].replace("-", " ")
        elif len(parts) == 2:
            course_code = parts[0]
            course_name = parts[1].replace("-", " ")
            term = "unknown"
        else:
            course_code = entry
            course_name = entry
            term = "unknown"

        courses.append({
            "course_code": course_code,
            "course_name": course_name,
            "term": term,
            "directory": entry_path,
        })

    logger.info(f"Found {len(courses)} verified courses in {base_dir}")
    return courses


def load_file(file_path: str) -> List[Document]:
    """Dispatches file loading based on extension. Returns list of Document objects."""
    basename = os.path.basename(file_path)
    if basename in SKIP_FILES or basename.startswith("."):
        return []

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        return []

    try:
        if ext == ".json":
            return _load_json(file_path)
        elif ext in (".pdf", ".pptx"):
            return _load_with_docling(file_path)
        else:
            return _load_text(file_path)
    except Exception as e:
        logger.error(f"Failed to load file {file_path}: {e}")
        return []


def _load_json(file_path: str) -> List[Document]:
    """Parse JSON file, extract content field, return as Document."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    content = data.get("content", "")
    title = data.get("title", "")
    if not content.strip():
        return []

    doc = Document(
        page_content=content,
        metadata={"title": title, "source": file_path},
    )
    return [doc]


_converter = None


def _get_converter():
    """Return a shared DocumentConverter singleton (avoids expensive re-init per file)."""
    global _converter
    if _converter is None:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions

        pipeline_options = PdfPipelineOptions(allow_external_plugins=True)
        _converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
    return _converter


def _load_with_docling(file_path: str) -> List[Document]:
    """Use DoclingLoader for PDF and PPTX files with DOC_CHUNKS mode for page metadata."""
    from langchain_docling import DoclingLoader
    from langchain_docling.loader import ExportType

    loader = DoclingLoader(
        file_path=file_path,
        converter=_get_converter(),
        export_type=ExportType.DOC_CHUNKS,
    )
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Token indices sequence length is longer than the specified maximum sequence length",
        )
        docs = loader.load()

    for doc in docs:
        # Extract page_number from dl_meta or top-level page_no
        page_number = doc.metadata.pop("page_no", None)
        if page_number is None:
            dl_meta = doc.metadata.get("dl_meta")
            if isinstance(dl_meta, dict):
                for item in dl_meta.get("doc_items", []):
                    for prov in item.get("prov", []):
                        if "page_no" in prov:
                            page_number = prov["page_no"]
                            break
                    if page_number is not None:
                        break
            elif isinstance(dl_meta, str):
                try:
                    meta_dict = json.loads(dl_meta)
                    for item in meta_dict.get("doc_items", []):
                        for prov in item.get("prov", []):
                            if "page_no" in prov:
                                page_number = prov["page_no"]
                                break
                        if page_number is not None:
                            break
                except (json.JSONDecodeError, TypeError):
                    pass
        doc.metadata["page_number"] = page_number
        # Remove dl_meta — it's a complex structure not useful to store raw
        doc.metadata.pop("dl_meta", None)

    return docs


def _load_text(file_path: str) -> List[Document]:
    """Read plain text files (.py, .txt, .md)."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    if not content.strip():
        return []

    doc = Document(
        page_content=content,
        metadata={"source": file_path},
    )
    return [doc]


def _load_and_tag(file_path: str, metadata: Dict[str, Any]) -> List[Document]:
    """Load a single file and attach metadata to all resulting documents."""
    docs = load_file(file_path)
    for doc in docs:
        doc.metadata.update(metadata)
    return docs


def load_course_documents(
    course_dir: str, course_metadata: Dict[str, Any]
) -> List[Document]:
    """Loads files from Syllabus/, Lectures/, Exercises/, References/ subdirectories."""
    documents = []

    for category in CONTENT_CATEGORIES:
        category_dir = os.path.join(course_dir, category)
        if not os.path.isdir(category_dir):
            continue

        for root, _dirs, files in os.walk(category_dir):
            for fname in sorted(files):
                file_path = os.path.join(root, fname)
                docs = load_file(file_path)
                lecture_number = _extract_lecture_number(fname)
                for doc in docs:
                    doc.metadata.update({
                        "source_type": "verified_content",
                        "course_code": course_metadata["course_code"],
                        "course_name": course_metadata["course_name"],
                        "term": course_metadata["term"],
                        "content_category": category,
                        "file_name": fname,
                        "lecture_number": lecture_number,
                    })
                documents.extend(docs)

    logger.info(
        f"Loaded {len(documents)} documents from course "
        f"{course_metadata['course_code']} ({course_metadata['course_name']})"
    )
    return documents


def load_all_verified_content(base_dir: str, max_workers: int = 4) -> List[Document]:
    """Top-level function returning flat list of Document objects from all courses.

    Files are loaded in parallel using a thread pool to speed up Docling conversion.
    """
    courses = scan_courses(base_dir)

    # Collect all (file_path, metadata) pairs across every course and category.
    file_tasks: List[Tuple[str, Dict[str, Any]]] = []
    for course in courses:
        for category in CONTENT_CATEGORIES:
            category_dir = os.path.join(course["directory"], category)
            if not os.path.isdir(category_dir):
                continue
            for root, _dirs, files in os.walk(category_dir):
                for fname in sorted(files):
                    file_path = os.path.join(root, fname)
                    meta = {
                        "source_type": "verified_content",
                        "course_code": course["course_code"],
                        "course_name": course["course_name"],
                        "term": course["term"],
                        "content_category": category,
                        "file_name": fname,
                        "lecture_number": _extract_lecture_number(fname),
                    }
                    file_tasks.append((file_path, meta))

    if not file_tasks:
        logger.info("No verified content files found.")
        return []

    # Process files in parallel.
    all_documents: List[Document] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_load_and_tag, path, meta): path
            for path, meta in file_tasks
        }
        for future in as_completed(futures):
            file_path = futures[future]
            try:
                docs = future.result()
                all_documents.extend(docs)
            except Exception as e:
                logger.error(f"Failed to load file {file_path}: {e}")

    logger.info(f"Total verified content documents loaded: {len(all_documents)}")
    return all_documents
