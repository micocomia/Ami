from __future__ import annotations

import re
from typing import Any


def _anchorize(title: str) -> str:
    anchor = re.sub(r"[^\w\s-]", "", str(title or "").lower()).strip().replace(" ", "-")
    return re.sub(r"-+", "-", anchor)


def _extract_headings(markdown: str) -> list[dict[str, Any]]:
    text = str(markdown or "")
    lines = text.splitlines(keepends=True)
    in_code_fence = False
    fence_token = ""
    headings: list[dict[str, Any]] = []
    offset = 0

    for line in lines:
        stripped = line.lstrip()
        fence_match = re.match(r"^(```|~~~)", stripped)
        if fence_match:
            token = fence_match.group(1)
            if not in_code_fence:
                in_code_fence = True
                fence_token = token
            elif token == fence_token:
                in_code_fence = False
                fence_token = ""
        if not in_code_fence:
            heading_match = re.match(r"^(#{2,3})\s+(.+?)\s*$", line)
            if heading_match:
                headings.append(
                    {
                        "level": len(heading_match.group(1)),
                        "title": heading_match.group(2).strip(),
                        "start": offset,
                    }
                )
        offset += len(line)
    return headings


def parse_document_for_section_view(document: str) -> dict[str, Any]:
    text = str(document or "")
    headings = _extract_headings(text)

    section_documents: list[str] = []
    sidebar_items: list[dict[str, Any]] = []
    references_section: str | None = None

    h2_headings = [item for item in headings if item["level"] == 2]
    for idx, item in enumerate(h2_headings):
        title = str(item.get("title", "")).strip()
        start = int(item.get("start", 0))
        end = int(h2_headings[idx + 1]["start"]) if idx + 1 < len(h2_headings) else len(text)
        section_text = text[start:end].strip()
        if title.lower() == "references":
            references_section = section_text
            continue
        section_documents.append(section_text)

    curr_l2 = 0
    curr_l3 = 0
    page_idx_counter = -1
    for item in headings:
        level = int(item.get("level", 0))
        title = str(item.get("title", "")).strip()
        if level == 2 and title.lower() == "references":
            continue
        if level == 2:
            page_idx_counter += 1
            curr_l2 += 1
            curr_l3 = 0
            sidebar_items.append(
                {
                    "title": f"{curr_l2}. {title}",
                    "anchor": _anchorize(title),
                    "level": 2,
                    "page_index": page_idx_counter,
                }
            )
        elif level == 3 and page_idx_counter >= 0:
            curr_l3 += 1
            sidebar_items.append(
                {
                    "title": f"{curr_l2}.{curr_l3}. {title}",
                    "anchor": _anchorize(title),
                    "level": 3,
                    "page_index": page_idx_counter,
                }
            )

    return {
        "section_documents": section_documents,
        "sidebar_items": sidebar_items,
        "references_section": references_section,
    }
