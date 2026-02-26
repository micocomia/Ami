import ast
import html
import re


def _source_dedup_key(source_ref):
    """Return a hashable key for deduplication of source references."""
    if isinstance(source_ref, dict):
        st = source_ref.get("source_type", "")
        if st == "verified_content":
            return (st, source_ref.get("file_name", ""))
        elif st == "web_search":
            return (st, source_ref.get("url", ""))
        else:
            return (st,)
    # Plain string (backward compat)
    return (str(source_ref),)


def extract_sources_used(knowledge_drafts):
    """Collect unique source references across all knowledge drafts.

    Handles both new dict-based refs and legacy plain-string refs.
    Deduplicates by composite key.
    """
    if isinstance(knowledge_drafts, str):
        knowledge_drafts = ast.literal_eval(knowledge_drafts)
    if not knowledge_drafts:
        return []

    sources = []
    seen_keys = set()
    for draft in knowledge_drafts:
        if isinstance(draft, dict):
            draft_sources = draft.get("sources_used") or []
            if not isinstance(draft_sources, list):
                continue
            for s in draft_sources:
                key = _source_dedup_key(s)
                if key not in seen_keys:
                    seen_keys.add(key)
                    sources.append(s)
    return sources


def format_citation(source_ref, index):
    """Return a human-readable citation string for a source reference."""
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
                label += f" — {course_name}"
            parts = []
            if lecture_number is not None:
                parts.append(f"Lecture {lecture_number}")
            if page_number is not None:
                parts.append(f"p.{page_number}")
            if parts:
                label += f" — {', '.join(parts)}"
            if file_name:
                label += f" ({file_name})"
            return f"[{index}] {label} — verified course material"
        elif st == "web_search":
            title = source_ref.get("title", "Web Source")
            url = source_ref.get("url", "")
            url_part = f" ({url})" if url else ""
            return f"[{index}] {title}{url_part} — web search"
        else:
            return f"[{index}] {st}"
    # Plain string fallback (backward compat)
    return f"[{index}] {source_ref}"


def _citation_tooltip_text(source_ref):
    """Return a short tooltip string for a source reference (no index prefix)."""
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
                label += f" \u2014 {course_name}"
            parts = []
            if lecture_number is not None:
                parts.append(f"Lecture {lecture_number}")
            if page_number is not None:
                parts.append(f"p.{page_number}")
            if parts:
                label += f" \u2014 {', '.join(parts)}"
            if file_name:
                label += f" ({file_name})"
            return label
        elif st == "web_search":
            title = source_ref.get("title", "Web Source")
            url = source_ref.get("url", "")
            url_part = f" ({url})" if url else ""
            return f"{title}{url_part}"
        else:
            return st
    return str(source_ref)


def inject_citation_tooltips(markdown_text, sources):
    """Replace [N] citation markers with HTML superscript spans that show a tooltip on hover.

    `sources` is the 1-indexed list returned by extract_sources_used().
    """
    if not sources:
        return markdown_text

    # Build a lookup: citation number -> tooltip text
    tooltip_map = {}
    for idx, source_ref in enumerate(sources, start=1):
        tooltip_map[idx] = html.escape(_citation_tooltip_text(source_ref), quote=True)

    def _replace_citation(match):
        num = int(match.group(1))
        tip = tooltip_map.get(num)
        if tip is None:
            return match.group(0)  # unknown citation, leave as-is
        return (
            f'<span title="{tip}" style="cursor:help; color:#1a73e8; font-weight:600;">'
            f'<sup>[{num}]</sup></span>'
        )

    # Match [N] but not when part of a markdown link [text](url)
    return re.sub(r'(?<!\[)\[(\d+)\](?!\()', _replace_citation, markdown_text)


def convert_knowledge_perspectives_to_markdown(data):
    markdown_text = ""
    for category, items in data.items():
        markdown_text += f"- **{category.capitalize()}**\n"
        for item in items:
            markdown_text += f"  - {item}\n"
    return markdown_text


def prepare_markdown_document(document_structure, knowledge_points, knowledge_drafts):
    if isinstance(knowledge_points, str):
        knowledge_points = ast.literal_eval(knowledge_points)
    if isinstance(knowledge_drafts, str):
        knowledge_drafts = ast.literal_eval(knowledge_drafts)
    if isinstance(document_structure, str):
        document_structure = ast.literal_eval(document_structure)
    print("!!!doucment_stru:",document_structure)
    part_titles = {
        'foundational': "## Foundational Concepts",
        'practical': "## Practical Applications",
        'strategic': "## Strategic Insights"
    }

    learning_document = f"# {document_structure['title']}"
    learning_document += f"\n\n{document_structure['overview']}"

    for k_type, part_title in part_titles.items():
        learning_document += f"\n\n{part_title}\n"
        for k_id, knowledge_point in enumerate(knowledge_points):
            if knowledge_point['type'] != k_type:
                continue
            knowledge_draft = knowledge_drafts[k_id]
            learning_document += f"\n\n### {knowledge_draft['title']}\n"
            learning_document += f"\n\n{knowledge_draft['content']}\n"
    learning_document += f"\n\n## Summary\n\n{document_structure['summary']}"

    # Collect all unique sources and append References section
    all_sources = extract_sources_used(knowledge_drafts)
    if all_sources:
        learning_document += "\n\n## References\n\n"
        for idx, source_ref in enumerate(all_sources, start=1):
            learning_document += format_citation(source_ref, idx) + "\n"

    return learning_document
