from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.documents import Document

from base.search_rag import SearchRagManager

_LOW_SIGNAL_MARKERS = (
    "for information about citing these materials",
    "terms of use",
    "ocw.mit.edu/terms",
    "download slides and .py files and follow along",
    "course policies",
)

_TOKEN_STOPWORDS = {
    "course", "content", "lecture", "lectures", "learn", "learning", "from",
    "about", "the", "and", "for", "with", "to", "in", "of", "stuff",
}


def _tokenize(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9][a-z0-9\.\-_]+", (text or "").lower())
        if len(t) > 1 and t not in _TOKEN_STOPWORDS
    }


def _topical_overlap(query: str, text: str) -> int:
    return len(_tokenize(query) & _tokenize(text))


def _is_low_signal_text(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    if any(marker in t for marker in _LOW_SIGNAL_MARKERS):
        return True
    alpha_chars = sum(1 for ch in t if ch.isalpha())
    return alpha_chars < 20


def _is_usable_doc(doc: Document) -> bool:
    return not _is_low_signal_text(doc.page_content)


def _score_doc(doc: Document, query: str) -> int:
    meta = doc.metadata or {}
    overlap = _topical_overlap(query, doc.page_content)
    lecture_boost = 2 if meta.get("lecture_number") is not None else 0
    signal_boost = 1 if _is_usable_doc(doc) else -2
    return overlap * 3 + lecture_boost + signal_boost


def _filter_category(docs: Sequence[Document], category: str) -> List[Document]:
    c = (category or "").lower()
    return [
        d for d in docs
        if str((d.metadata or {}).get("content_category", "")).lower() == c
    ]


def _normalize_lecture_numbers(value: Any) -> List[int]:
    if value is None:
        return []
    if isinstance(value, int):
        nums = [value]
    elif isinstance(value, list):
        nums = [x for x in value if isinstance(x, int)]
    else:
        return []
    nums = sorted({n for n in nums if n > 0})
    return nums


def _cap_lecture_numbers(nums: List[int], cap: int = 20) -> List[int]:
    return nums[:cap]


def _retrieve_filtered_or_basic(
    vcm: Any,
    *,
    query: str,
    k: int,
    course_code: Optional[str],
    content_category: Optional[str],
    lecture_number: Optional[int],
    page_number: Optional[int],
    exclude_file_names: Optional[List[str]] = None,
    require_lecture: bool = False,
) -> List[Document]:
    if hasattr(type(vcm), "retrieve_filtered"):
        return vcm.retrieve_filtered(
            query=query,
            k=k,
            course_code=course_code,
            content_category=content_category,
            lecture_number=lecture_number,
            page_number=page_number,
            exclude_file_names=exclude_file_names,
            require_lecture=require_lecture,
        )
    docs = vcm.retrieve(query, k=k)
    if content_category:
        docs = _filter_category(docs, content_category)
    if lecture_number is not None:
        docs = [
            d for d in docs
            if (d.metadata or {}).get("lecture_number") == lecture_number
        ]
    if course_code:
        docs = [
            d for d in docs
            if str((d.metadata or {}).get("course_code", "")).lower() == course_code.lower()
        ]
    return docs


def _select_lecture_diverse_docs(docs: Sequence[Document], query: str, k: int) -> List[Document]:
    ranked = sorted(docs, key=lambda d: _score_doc(d, query), reverse=True)
    selected: List[Document] = []
    used_buckets: set[str] = set()

    def bucket(doc: Document) -> str:
        meta = doc.metadata or {}
        lec = meta.get("lecture_number")
        if lec is not None:
            return f"lecture:{lec}"
        file_name = str(meta.get("file_name", "")).strip().lower()
        return f"file:{file_name}" if file_name else "unknown"

    # Pass 1: one per lecture/file bucket
    for doc in ranked:
        b = bucket(doc)
        if b in used_buckets:
            continue
        used_buckets.add(b)
        selected.append(doc)
        if len(selected) >= k:
            return selected

    # Pass 2: fill remainder by score
    for doc in ranked:
        if doc in selected:
            continue
        selected.append(doc)
        if len(selected) >= k:
            break

    return selected


def _two_stage_merge(
    syllabus_docs: Sequence[Document],
    lecture_docs: Sequence[Document],
    query: str,
    total_k: int = 8,
    syllabus_quota: int = 2,
    lecture_quota: int = 6,
) -> List[Document]:
    top_syllabus = sorted(syllabus_docs, key=lambda d: _score_doc(d, query), reverse=True)[:syllabus_quota]
    top_lectures = _select_lecture_diverse_docs(lecture_docs, query, lecture_quota)

    selected = list(top_syllabus) + list(top_lectures)
    if len(selected) >= total_k:
        return selected[:total_k]

    # Backfill from remaining syllabus then remaining lectures
    remainder_syllabus = [d for d in sorted(syllabus_docs, key=lambda d: _score_doc(d, query), reverse=True) if d not in selected]
    remainder_lectures = [d for d in sorted(lecture_docs, key=lambda d: _score_doc(d, query), reverse=True) if d not in selected]
    for pool in (remainder_syllabus, remainder_lectures):
        for doc in pool:
            selected.append(doc)
            if len(selected) >= total_k:
                return selected
    return selected


def _retrieve_context_for_goal(
    goal_context: Dict[str, Any],
    search_rag_manager: Optional[SearchRagManager],
) -> List[Document]:
    """Deterministically retrieve course content using parsed goal context."""
    if search_rag_manager is None or search_rag_manager.verified_content_manager is None:
        return []

    vcm = search_rag_manager.verified_content_manager
    course_code = goal_context.get("course_code")
    lecture_numbers = _cap_lecture_numbers(_normalize_lecture_numbers(goal_context.get("lecture_numbers")), cap=20)
    lecture_number = lecture_numbers[0] if len(lecture_numbers) == 1 else None
    content_category = goal_context.get("content_category")
    page_number = goal_context.get("page_number")
    has_lecture_list = len(lecture_numbers) > 1
    is_broad_course_goal = bool(course_code) and not lecture_numbers and content_category is None and page_number is None

    query_parts = [p for p in [
        f"course {course_code}" if course_code else None,
        f"lectures {','.join(str(x) for x in lecture_numbers)}" if lecture_numbers else None,
        "content",
    ] if p]
    query = " ".join(query_parts)

    # Multi-lecture requests: retrieve per lecture, then select diverse top-k.
    if has_lecture_list:
        candidates: List[Document] = []
        seen = set()
        for ln in lecture_numbers:
            docs = _retrieve_filtered_or_basic(
                vcm,
                query=query,
                k=8,
                course_code=course_code,
                content_category=content_category or "Lectures",
                lecture_number=ln,
                page_number=page_number,
                exclude_file_names=["syllabus.json"],
                require_lecture=True,
            )
            for d in docs:
                meta = d.metadata or {}
                key = (
                    str(meta.get("course_code", "")),
                    str(meta.get("lecture_number", "")),
                    str(meta.get("file_name", "")),
                    str(meta.get("page_number", "")),
                    d.page_content[:120],
                )
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(d)
        return _select_lecture_diverse_docs(candidates, query, k=8)

    # Broad course goals: syllabus-first, fallback to lecture-diverse context if weak.
    if is_broad_course_goal:
        # Legacy fallback path: if metadata-filtered retrieval is unavailable,
        # keep a single basic retrieve call to avoid duplicated generic fetches.
        if not hasattr(type(vcm), "retrieve_filtered"):
            return vcm.retrieve(query, k=8)

        syllabus_docs = _retrieve_filtered_or_basic(
            vcm,
            query=query,
            k=8,
            course_code=course_code,
            content_category="Syllabus",
            lecture_number=None,
            page_number=None,
            exclude_file_names=None,
            require_lecture=False,
        )
        usable_syllabus = [d for d in syllabus_docs if _is_usable_doc(d)]
        if usable_syllabus:
            low_overlap_count = sum(1 for d in usable_syllabus if _topical_overlap(query, d.page_content) <= 0)
            weak_by_overlap = low_overlap_count >= math.ceil(0.6 * len(usable_syllabus))
        else:
            weak_by_overlap = True
        weak_signal = len(usable_syllabus) < 3 or weak_by_overlap

        if not weak_signal:
            return sorted(usable_syllabus, key=lambda d: _score_doc(d, query), reverse=True)[:8]

        lecture_docs = _retrieve_filtered_or_basic(
            vcm,
            query=query,
            k=24,
            course_code=course_code,
            content_category="Lectures",
            lecture_number=None,
            page_number=None,
            exclude_file_names=["syllabus.json"],
            require_lecture=True,
        )
        usable_lectures = [d for d in lecture_docs if _is_usable_doc(d)]
        merged = _two_stage_merge(
            syllabus_docs=usable_syllabus,
            lecture_docs=usable_lectures,
            query=query,
            total_k=8,
            syllabus_quota=2,
            lecture_quota=6,
        )
        return merged[:8]

    effective_category = content_category or ("Lectures" if lecture_numbers else None)
    require_lecture = bool(effective_category == "Lectures") if effective_category else bool(lecture_numbers)
    exclude = ["syllabus.json"] if require_lecture else None

    return _retrieve_filtered_or_basic(
        vcm,
        query=query,
        k=8,
        course_code=course_code,
        content_category=effective_category,
        lecture_number=lecture_number,
        page_number=page_number,
        exclude_file_names=exclude,
        require_lecture=require_lecture,
    )
