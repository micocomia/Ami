from __future__ import annotations

import ast
import re
from typing import Any, Mapping, Optional, List
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, field_validator

from base import BaseAgent
from base.search_rag import SearchRagManager, format_docs
from modules.content_generator.prompts.search_enhanced_knowledge_drafter import (
    search_enhanced_knowledge_drafter_system_prompt,
    search_enhanced_knowledge_drafter_task_prompt,
)
from modules.content_generator.schemas import KnowledgeDraft
from config.loader import default_config


class KnowledgeDraftPayload(BaseModel):
    learner_profile: Any
    learning_path: Any
    learning_session: Any
    knowledge_points: Any
    knowledge_point: Any
    external_resources: str | None = ""
    visual_formatting_hints: str = ""
    processing_perception_hints: str = ""

    @field_validator("learner_profile", "learning_path", "learning_session", "knowledge_points", "knowledge_point")
    @classmethod
    def coerce_jsonish(cls, v: Any) -> Any:
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, Mapping):
            return dict(v)
        if isinstance(v, str):
            return v.strip()
        return v


class SearchEnhancedKnowledgeDrafter(BaseAgent):
    _NOISE_TOKENS = {
        "lecture", "lectures", "course", "courses", "today", "welcome",
        "download", "slides", "files", "follow", "along", "introduction",
        "information", "terms", "use", "ocw", "mit", "python", "fall",
    }

    name: str = "SearchEnhancedKnowledgeDrafter"

    def __init__(self, model: Any, *, search_rag_manager: Optional[SearchRagManager] = None, use_search: bool = True):
        super().__init__(model=model, system_prompt=search_enhanced_knowledge_drafter_system_prompt, jsonalize_output=True)
        self.search_rag_manager = search_rag_manager or SearchRagManager.from_config(default_config)
        self.use_search = use_search

    @staticmethod
    def _extract_course_codes(*texts: str) -> List[str]:
        pat = re.compile(r"\b\d+\.\d+\b|\b[A-Za-z]+\d{3,}\b|\b\d+[A-Za-z]+\d*\b")
        out: List[str] = []
        for t in texts:
            if not t:
                continue
            for c in pat.findall(t):
                if c not in out:
                    out.append(c)
        return out

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        toks = {
            t for t in re.findall(r"[a-z0-9][a-z0-9\.\-_]+", (text or "").lower())
            if len(t) > 1
        }
        return {t for t in toks if t not in SearchEnhancedKnowledgeDrafter._NOISE_TOKENS}

    @staticmethod
    def _is_lecture_doc(meta: Mapping[str, Any]) -> bool:
        if meta.get("lecture_number") is not None:
            return True
        category = str(meta.get("content_category", "")).lower().strip()
        if category == "lectures":
            return True
        file_name = str(meta.get("file_name", "")).lower().strip()
        return file_name.startswith("lec_") and file_name.endswith(".pdf")

    @staticmethod
    def _is_low_signal_text(text: str) -> bool:
        t = (text or "").strip().lower()
        if not t:
            return True
        # MIT OCW footer/citation boilerplate appears frequently in slide PDFs.
        boilerplate_markers = [
            "for information about citing these materials",
            "terms of use",
            "ocw.mit.edu/terms",
        ]
        if any(m in t for m in boilerplate_markers):
            return True
        if "download slides and .py files and follow along" in t:
            return True
        if t.startswith("welcome!"):
            return True
        if "today" in t and "course info" in t:
            return True
        alpha_chars = sum(1 for ch in t if ch.isalpha())
        if alpha_chars < 40:
            return True
        return False

    def _match_course_code(self, doc: Any, course_codes: List[str]) -> bool:
        if not course_codes:
            return True
        meta = doc.metadata or {}
        code = str(meta.get("course_code", "")).lower().strip()
        if not code:
            return True
        wanted = {c.lower() for c in course_codes}
        return code in wanted

    def _doc_overlap(self, doc: Any, intent_tokens: set[str]) -> int:
        meta = doc.metadata or {}
        meta_text = " ".join([
            str(meta.get("title", "")),
            str(meta.get("course_code", "")),
            str(meta.get("course_name", "")),
            str(meta.get("file_name", "")),
            str(meta.get("content_category", "")),
        ])
        doc_tokens = self._tokenize(f"{meta_text} {doc.page_content}")
        return len(intent_tokens & doc_tokens)

    @staticmethod
    def _as_mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = ast.literal_eval(value)
                if isinstance(parsed, Mapping):
                    return dict(parsed)
            except Exception:
                return {}
        return {}

    def _build_query_bundle(self, data: dict[str, Any]) -> tuple[list[str], str]:
        session = self._as_mapping(data.get("learning_session"))
        profile = self._as_mapping(data.get("learner_profile"))
        learning_path = self._as_mapping(data.get("learning_path"))
        knowledge_point = self._as_mapping(data.get("knowledge_point"))

        session_title = str(session.get("title", "")).strip()
        kp_name = str(knowledge_point.get("name", "")).strip()
        kp_type = str(knowledge_point.get("type", "")).strip()

        goal_candidates = [
            str(profile.get("learning_goal", "")).strip(),
            str(profile.get("refined_goal", "")).strip(),
            str(profile.get("goal", "")).strip(),
            str(learning_path.get("learning_goal", "")).strip(),
            str(learning_path.get("refined_goal", "")).strip(),
            str(data.get("learning_goal", "")).strip(),
        ]
        learning_goal = next((g for g in goal_candidates if g), "")

        course_codes = self._extract_course_codes(session_title, kp_name, learning_goal)
        course_hint = " ".join(course_codes).strip()

        base = " ".join(x for x in [session_title, kp_name, kp_type, learning_goal, course_hint] if x).strip()
        queries = []
        for q in [
            base,
            " ".join(x for x in [kp_name, learning_goal, course_hint] if x).strip(),
            " ".join(x for x in [session_title, kp_name, course_hint] if x).strip(),
            " ".join(x for x in [kp_name, course_hint] if x).strip(),
        ]:
            if q and q not in queries:
                queries.append(q)
        return queries[:3], base

    def _rank_docs(self, docs: List[Any], intent_text: str) -> List[Any]:
        intent_tokens = self._tokenize(intent_text)

        def score(doc: Any) -> tuple[int, int]:
            meta = doc.metadata or {}
            st = str(meta.get("source_type", "")).lower()
            file_name = str(meta.get("file_name", "")).lower().strip()
            overlap = self._doc_overlap(doc, intent_tokens)
            verified_boost = 3 if st == "verified_content" else 0
            lecture_boost = 4 if self._is_lecture_doc(meta) else 0
            syllabus_penalty = -2 if "syllabus" in file_name else 0
            return (overlap + verified_boost + lecture_boost + syllabus_penalty, overlap)

        return sorted(docs, key=score, reverse=True)

    def draft(self, payload: KnowledgeDraftPayload | Mapping[str, Any] | str):
        if not isinstance(payload, KnowledgeDraftPayload):
            payload = KnowledgeDraftPayload.model_validate(payload)
        data = payload.model_dump()
        # Optionally enrich external resources using the search RAG manager
        sources_used = []
        if self.use_search and self.search_rag_manager is not None:
            queries, intent_text = self._build_query_bundle(data)
            base_k = max(1, int(getattr(self.search_rag_manager, "max_retrieval_results", 5)))
            # Retrieve more candidates than default, then rerank down to a cleaner final set.
            fetch_k = max(base_k * 3, 12)
            final_k = max(base_k + 2, 7)
            course_codes = self._extract_course_codes(intent_text)
            primary_course_code = course_codes[0] if course_codes else None
            lecture_intent = "lecture" in intent_text.lower()

            candidates = []
            seen = set()
            for q in queries:
                if primary_course_code:
                    docs = self.search_rag_manager.invoke_hybrid_filtered(
                        q,
                        k=fetch_k,
                        course_code=primary_course_code,
                        content_category="Lectures" if lecture_intent else None,
                        exclude_file_names=["syllabus.json"],
                        require_lecture=lecture_intent,
                        allow_web_fallback=False,
                    )
                else:
                    docs = self.search_rag_manager.invoke_hybrid(q, k=fetch_k)
                for d in docs:
                    meta = d.metadata or {}
                    key = (
                        str(meta.get("source_type", "")),
                        str(meta.get("course_code", "")),
                        str(meta.get("file_name", "")),
                        str(meta.get("page_number", "")),
                        d.page_content[:180],
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(d)

            intent_tokens = self._tokenize(intent_text)
            filtered = [
                d for d in candidates
                if self._match_course_code(d, course_codes) and not self._is_low_signal_text(d.page_content)
            ]
            # For lecture-targeted requests, suppress syllabus/admin chunks.
            if lecture_intent:
                lecture_filtered = [d for d in filtered if self._is_lecture_doc(d.metadata or {})]
                if lecture_filtered:
                    filtered = lecture_filtered
            # Require minimal lexical overlap with intent to reduce off-topic chunks.
            strong = [d for d in filtered if self._doc_overlap(d, intent_tokens) >= 2]
            if strong:
                filtered = strong
            if not filtered:
                # Fallback: keep course-matching docs even if low-signal filtering is too strict.
                filtered = [d for d in candidates if self._match_course_code(d, course_codes)]
            if not filtered:
                filtered = candidates

            # Prefer lecture chunks; use non-lecture docs only as backfill.
            lecture_docs = [d for d in filtered if self._is_lecture_doc(d.metadata or {})]
            if lecture_docs:
                pool = lecture_docs + [d for d in filtered if d not in lecture_docs]
            else:
                pool = filtered

            docs = self._rank_docs(pool, intent_text)[:final_k]
            # Collect detailed source references (ordered by same index as format_docs)
            for idx, doc in enumerate(docs):
                meta = doc.metadata or {}
                st = meta.get("source_type")
                if st == "verified_content":
                    ref = {
                        "source_type": "verified_content",
                        "course_code": meta.get("course_code", ""),
                        "course_name": meta.get("course_name", ""),
                        "lecture_number": meta.get("lecture_number"),
                        "page_number": meta.get("page_number"),
                        "file_name": meta.get("file_name", ""),
                        "page_content": doc.page_content,
                    }
                elif st == "web_search":
                    ref = {
                        "source_type": "web_search",
                        "title": meta.get("title", ""),
                        "url": meta.get("source", ""),
                        "page_content": doc.page_content,
                    }
                else:
                    ref = {"source_type": st or "unknown", "page_content": doc.page_content}
                sources_used.append(ref)
            context = format_docs(docs)
            if context:
                ext = data.get("external_resources") or ""
                data["external_resources"] = f"{ext}{context}"
        raw_output = self.invoke(data, task_prompt=search_enhanced_knowledge_drafter_task_prompt)
        validated_output = KnowledgeDraft.model_validate(raw_output)
        result = validated_output.model_dump()
        if sources_used:
            result["sources_used"] = sources_used
        return result

def draft_knowledge_point_with_llm(
    llm,
    learner_profile,
    learning_path,
    learning_session,
    knowledge_points,
    knowledge_point,
    use_search: bool = True,
    visual_formatting_hints: str = "",
    processing_perception_hints: str = "",
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
):
    """Draft a single knowledge point using the agent, optionally enriching with a SearchRagManager."""
    drafter = SearchEnhancedKnowledgeDrafter(llm, search_rag_manager=search_rag_manager, use_search=use_search)
    payload = {
        "learner_profile": learner_profile,
        "learning_path": learning_path,
        "learning_session": learning_session,
        "knowledge_points": knowledge_points,
        "knowledge_point": knowledge_point,
        "visual_formatting_hints": visual_formatting_hints,
        "processing_perception_hints": processing_perception_hints,
    }
    return drafter.draft(payload)


def draft_knowledge_points_with_llm(
    llm,
    learner_profile,
    learning_path,
    learning_session,
    knowledge_points,
    allow_parallel: bool = True,
    use_search: bool = True,
    max_workers: int = 8,
    visual_formatting_hints: str = "",
    processing_perception_hints: str = "",
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
):
    """Draft multiple knowledge points in parallel or sequentially using the agent."""
    if isinstance(learning_session, str):
        learning_session = ast.literal_eval(learning_session)
    if isinstance(knowledge_points, str):
        knowledge_points = ast.literal_eval(knowledge_points)
    if search_rag_manager is None and use_search:
        search_rag_manager = SearchRagManager.from_config(default_config)
    def draft_one(kp):
        return draft_knowledge_point_with_llm(
            llm,
            learner_profile,
            learning_path,
            learning_session,
            knowledge_points,
            kp,
            use_search=use_search,
            visual_formatting_hints=visual_formatting_hints,
            processing_perception_hints=processing_perception_hints,
            search_rag_manager=search_rag_manager,
        )

    if allow_parallel:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(draft_one, knowledge_points))
    else:
        results: List[Any] = []
        for kp in knowledge_points:
            results.append(draft_one(kp))
        return results
