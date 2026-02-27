from __future__ import annotations

import html
import re
from typing import Any


def _source_label(source_ref: Any, index: int) -> str:
    if isinstance(source_ref, dict):
        st = source_ref.get("source_type", "")
        if st == "verified_content":
            course_code = source_ref.get("course_code", "")
            course_name = source_ref.get("course_name", "")
            lecture_number = source_ref.get("lecture_number")
            page_number = source_ref.get("page_number")
            file_name = source_ref.get("file_name", "")
            label = f"MIT {course_code}" if course_code else "Verified Course"
            if course_name:
                label += f" - {course_name}"
            parts = []
            if lecture_number is not None:
                parts.append(f"Lecture {lecture_number}")
            if page_number is not None:
                parts.append(f"p.{page_number}")
            if parts:
                label += f" - {', '.join(parts)}"
            if file_name:
                label += f" ({file_name})"
            return f"[{index}] {label} - verified course material"
        if st == "web_search":
            title = source_ref.get("title", "Web Source")
            url = source_ref.get("url", "")
            url_part = f" ({url})" if url else ""
            return f"[{index}] {title}{url_part} - web search"
        return f"[{index}] {st}"
    return f"[{index}] {source_ref}"


def _source_tooltip(source_ref: Any) -> str:
    if isinstance(source_ref, dict):
        st = source_ref.get("source_type", "")
        if st == "verified_content":
            course_code = source_ref.get("course_code", "")
            course_name = source_ref.get("course_name", "")
            lecture_number = source_ref.get("lecture_number")
            page_number = source_ref.get("page_number")
            file_name = source_ref.get("file_name", "")
            label = f"MIT {course_code}" if course_code else "Verified Course"
            if course_name:
                label += f" - {course_name}"
            parts = []
            if lecture_number is not None:
                parts.append(f"Lecture {lecture_number}")
            if page_number is not None:
                parts.append(f"p.{page_number}")
            if parts:
                label += f" - {', '.join(parts)}"
            if file_name:
                label += f" ({file_name})"
            return label
        if st == "web_search":
            title = source_ref.get("title", "Web Source")
            url = source_ref.get("url", "")
            return f"{title} ({url})" if url else title
        return st
    return str(source_ref)


def _anchorize(title: str) -> str:
    anchor = re.sub(r"[^\w\s-]", "", title.lower()).strip().replace(" ", "-")
    return re.sub(r"-+", "-", anchor)


def build_learning_content_view_model(document: str, sources_used: list[Any] | None, *, content_format: str = "standard", audio_mode: str | None = None) -> dict[str, Any]:
    if not isinstance(document, str):
        document = str(document or "")
    sources_used = sources_used or []

    titles = re.findall(r'^(#+)\s*(.*)', document, re.MULTILINE)
    section_starts = []
    start_idx = 0
    for marks, title in titles:
        if marks == "#":
            continue
        if marks == "##":
            start_idx = document.find(title, start_idx)
            section_starts.append((start_idx - 3, title.strip()))

    sections = []
    references = []
    toc = []
    for index, source_ref in enumerate(sources_used, start=1):
        references.append({
            "index": index,
            "label": _source_label(source_ref, index),
            "tooltip": html.escape(_source_tooltip(source_ref), quote=True),
            "source_type": source_ref.get("source_type") if isinstance(source_ref, dict) else "text",
            "url": source_ref.get("url") if isinstance(source_ref, dict) else None,
        })

    for i, (start, title) in enumerate(section_starts):
        end_idx = section_starts[i + 1][0] if i + 1 < len(section_starts) else len(document)
        section_text = document[start:end_idx - 1].strip()
        if section_text.startswith("## References"):
            continue
        anchor = _anchorize(title)
        citations = [int(num) for num in re.findall(r'(?<!\[)\[(\d+)\](?!\()', section_text)]
        section = {
            "id": f"section-{i}",
            "title": title,
            "level": 2,
            "anchor": anchor,
            "section_index": len(sections),
            "markdown": section_text,
            "html": None,
            "citations": citations,
            "show_quiz_after": False,
            "asset_urls": re.findall(r'(/static/[^\s)"\']+)', section_text),
        }
        sections.append(section)
        toc.append({
            "id": section["id"],
            "title": title,
            "level": 2,
            "anchor": anchor,
            "section_index": section["section_index"],
        })

    if sections:
        sections[-1]["show_quiz_after"] = True

    display_hints = {"banner_variant": content_format, "banner_text": None}
    if content_format == "audio_enhanced":
        if audio_mode == "narration_optional":
            display_hints["banner_text"] = "This lesson keeps written content and offers an optional narrated audio version."
        else:
            display_hints["banner_text"] = "This lesson keeps written content and offers an optional host-expert audio version."
    elif content_format == "visual_enhanced":
        display_hints["banner_text"] = "This content includes visual resources for visual learners."

    return {
        "sections": sections,
        "toc": toc,
        "references": references,
        "display_hints": display_hints,
    }
