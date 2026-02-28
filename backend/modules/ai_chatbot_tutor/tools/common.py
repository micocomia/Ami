from __future__ import annotations

import re
from typing import Dict, List


def _tokenize(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(t) > 2
    }


def _truncate(text: str, max_chars: int) -> str:
    raw = str(text or "").strip()
    if len(raw) <= max_chars:
        return raw
    return raw[: max(0, max_chars - 3)].rstrip() + "..."


def _split_markdown_sections(document: str) -> List[Dict[str, str]]:
    text = str(document or "")
    if not text.strip():
        return []

    lines = text.splitlines()
    sections: List[Dict[str, str]] = []
    current_title = "Overview"
    current_body: List[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_body:
                sections.append({
                    "title": current_title,
                    "body": "\n".join(current_body).strip(),
                })
            current_title = line[3:].strip() or "Section"
            current_body = []
            continue
        current_body.append(line)

    if current_body:
        sections.append({
            "title": current_title,
            "body": "\n".join(current_body).strip(),
        })

    return [s for s in sections if s.get("body")]


def _section_snippet(document: str, query: str, max_chars: int = 900) -> str:
    sections = _split_markdown_sections(document)
    if not sections:
        return _truncate(document, max_chars)

    query_tokens = _tokenize(query)
    if not query_tokens:
        top = sections[0]
        return f"{top['title']}\n{_truncate(top['body'], max_chars)}"

    scored = []
    for sec in sections:
        sec_tokens = _tokenize(f"{sec.get('title', '')} {sec.get('body', '')}")
        overlap = len(query_tokens.intersection(sec_tokens))
        scored.append((overlap, sec))
    scored.sort(key=lambda x: x[0], reverse=True)

    best = scored[0][1]
    return f"{best['title']}\n{_truncate(best.get('body', ''), max_chars)}"


def _message_tokens_overlap_score(text: str, query: str) -> int:
    return len(_tokenize(text).intersection(_tokenize(query)))
