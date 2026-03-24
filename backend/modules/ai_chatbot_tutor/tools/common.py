from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, MutableMapping


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


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def _ensure_retrieval_trace(sink: MutableMapping[str, Any] | None) -> MutableMapping[str, Any] | None:
    if sink is None:
        return None
    trace = sink.setdefault("retrieval_trace", {})
    if not isinstance(trace, MutableMapping):
        trace = {}
        sink["retrieval_trace"] = trace
    trace.setdefault("contexts", [])
    trace.setdefault("tool_calls", [])
    trace.setdefault("_context_keys", [])
    return trace


def _record_tool_call(
    sink: MutableMapping[str, Any] | None,
    *,
    tool_name: str,
    query: str,
    status: str,
    result_count: int = 0,
    extra: Mapping[str, Any] | None = None,
) -> None:
    trace = _ensure_retrieval_trace(sink)
    if trace is None:
        return
    payload = {
        "tool_name": tool_name,
        "query": str(query or ""),
        "status": str(status or "ok"),
        "result_count": int(result_count or 0),
    }
    if extra:
        payload.update({str(k): _json_safe(v) for k, v in extra.items()})
    trace["tool_calls"].append(payload)


def _record_contexts(
    sink: MutableMapping[str, Any] | None,
    *,
    tool_name: str,
    query: str,
    contexts: list[Mapping[str, Any]],
) -> None:
    trace = _ensure_retrieval_trace(sink)
    if trace is None:
        return

    seen_keys = trace.setdefault("_context_keys", [])
    if not isinstance(seen_keys, list):
        seen_keys = []
        trace["_context_keys"] = seen_keys

    for context in contexts:
        normalized = {str(k): _json_safe(v) for k, v in context.items()}
        normalized["tool_name"] = tool_name
        normalized["query"] = str(query or "")
        key = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
        if key in seen_keys:
            continue
        seen_keys.append(key)
        trace["contexts"].append(normalized)


def _document_to_trace_context(doc: Any) -> Dict[str, Any]:
    page_content = str(getattr(doc, "page_content", "") or "")
    metadata = getattr(doc, "metadata", {}) or {}
    if not isinstance(metadata, Mapping):
        metadata = {}

    return {
        "page_content": page_content,
        "source_type": metadata.get("source_type"),
        "course_code": metadata.get("course_code"),
        "file_name": metadata.get("file_name"),
        "lecture_number": metadata.get("lecture_number"),
        "title": metadata.get("title"),
        "source": metadata.get("source"),
        "url": metadata.get("url"),
        "metadata": _json_safe(dict(metadata)),
    }
