from __future__ import annotations

import ast
import re
from collections import defaultdict
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
from .knowledge_draft_evaluator import (
    deterministic_knowledge_draft_audit,
    evaluate_knowledge_draft_with_llm,
)
from modules.content_generator.utils import (
    build_session_adaptation_contract,
    format_session_adaptation_contract,
)
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
    session_adaptation_contract: Any = ""
    goal_context: Optional[Mapping[str, Any]] = None
    evaluator_feedback: str = ""

    @field_validator(
        "learner_profile",
        "learning_path",
        "learning_session",
        "knowledge_points",
        "knowledge_point",
        "session_adaptation_contract",
    )
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
    _QUERY_STOPWORDS = {
        "using", "explain", "teach", "focus", "overview", "topic", "topics",
        "knowledge", "point", "points", "material", "materials", "session",
        "goal", "learn", "learning", "content", "beginner", "basics",
        "basics", "style", "with", "from", "into", "about",
    }
    _GENERIC_CHUNK_MARKERS = (
        "overview of course",
        "what do computer scientists do",
        "hope we have started you down the path",
        "download slides and .py files and follow along",
        "for information about citing these materials",
    )

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
        return {
            t for t in toks
            if t not in SearchEnhancedKnowledgeDrafter._NOISE_TOKENS
            and t not in SearchEnhancedKnowledgeDrafter._QUERY_STOPWORDS
        }

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
        doc_tokens = self._doc_tokens(doc)
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

    @staticmethod
    def _normalize_lecture_numbers(value: Any) -> List[int]:
        if value is None:
            return []
        if isinstance(value, int):
            nums = [value]
        elif isinstance(value, list):
            nums = [x for x in value if isinstance(x, int)]
        else:
            return []
        return sorted({n for n in nums if n > 0})

    def _goal_retrieval_filters(self, value: Any) -> dict[str, Any]:
        ctx = self._as_mapping(value)
        # Use `or ""` before str() so that Python None is not converted to the
        # string "None", which would be truthy and incorrectly activate RAG.
        course_code = str(ctx.get("course_code") or "").strip() or None
        content_category = str(ctx.get("content_category") or "").strip() or None
        page_number = ctx.get("page_number")
        if not isinstance(page_number, int) or page_number <= 0:
            page_number = None
        lecture_numbers = self._normalize_lecture_numbers(
            ctx.get("lecture_numbers", ctx.get("lecture_number"))
        )
        has_retrieval_fields = any(
            [
                course_code,
                lecture_numbers,
                content_category,
                page_number,
            ]
        )
        return {
            "course_code": course_code,
            "content_category": content_category,
            "page_number": page_number,
            "lecture_numbers": lecture_numbers,
            "has_retrieval_fields": has_retrieval_fields,
        }

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

    def _doc_tokens(self, doc: Any) -> set[str]:
        meta = doc.metadata or {}
        meta_text = " ".join([
            str(meta.get("title", "")),
            str(meta.get("course_code", "")),
            str(meta.get("course_name", "")),
            str(meta.get("file_name", "")),
            str(meta.get("content_category", "")),
        ])
        return self._tokenize(f"{meta_text} {doc.page_content}")

    def _score_doc(self, doc: Any, intent_tokens: set[str], kp_tokens: set[str], kp_text: str = "") -> tuple[int, int, int]:
        meta = doc.metadata or {}
        st = str(meta.get("source_type", "")).lower()
        file_name = str(meta.get("file_name", "")).lower().strip()
        doc_text = f"{' '.join(str(meta.get(k, '')) for k in ['title', 'course_code', 'course_name', 'file_name', 'content_category'])} {doc.page_content}".lower()
        doc_tokens = self._doc_tokens(doc)
        overlap = len(intent_tokens & doc_tokens)
        kp_overlap = len(kp_tokens & doc_tokens) if kp_tokens else 0
        verified_boost = 3 if st == "verified_content" else 0
        lecture_boost = 4 if self._is_lecture_doc(meta) else 0
        syllabus_penalty = -3 if "syllabus" in file_name else 0
        generic_penalty = -4 if any(m in doc_text for m in self._GENERIC_CHUNK_MARKERS) else 0
        low_signal_penalty = -2 if self._is_low_signal_text(doc.page_content) else 0
        phrase_boost = 2 if kp_text and kp_text.lower() in doc_text else 0
        total = (
            (overlap * 2)
            + (kp_overlap * 3)
            + phrase_boost
            + verified_boost
            + lecture_boost
            + syllabus_penalty
            + generic_penalty
            + low_signal_penalty
        )
        return (total, kp_overlap, overlap)

    def _rank_docs(self, docs: List[Any], intent_text: str, kp_text: str = "") -> List[Any]:
        intent_tokens = self._tokenize(intent_text)
        kp_tokens = self._tokenize(kp_text)
        return sorted(
            docs,
            key=lambda d: self._score_doc(d, intent_tokens, kp_tokens, kp_text),
            reverse=True,
        )

    @staticmethod
    def _doc_file_bucket(doc: Any) -> str:
        meta = doc.metadata or {}
        file_name = str(meta.get("file_name", "")).strip().lower()
        if file_name:
            return file_name
        source = str(meta.get("source", "")).strip().lower()
        return source or "unknown"

    def _select_diverse_docs(self, ranked_docs: List[Any], k: int, max_per_file: int = 2) -> List[Any]:
        if k <= 0:
            return []
        picked: List[Any] = []
        per_file_counts: dict[str, int] = defaultdict(int)

        for doc in ranked_docs:
            bucket = self._doc_file_bucket(doc)
            if per_file_counts[bucket] >= max_per_file:
                continue
            picked.append(doc)
            per_file_counts[bucket] += 1
            if len(picked) >= k:
                return picked

        for doc in ranked_docs:
            if doc in picked:
                continue
            picked.append(doc)
            if len(picked) >= k:
                break
        return picked

    def _select_coverage_diverse_docs(
        self,
        ranked_docs: List[Any],
        k: int,
        *,
        intent_text: str,
        kp_text: str = "",
        max_per_file: int = 2,
    ) -> List[Any]:
        """
        Greedy coverage-aware selector:
        - maximize new concept-token coverage first
        - then prefer higher-quality chunks
        - maintain file diversity with max_per_file cap
        """
        if k <= 0 or not ranked_docs:
            return []

        intent_tokens = self._tokenize(intent_text)
        kp_tokens = self._tokenize(kp_text)
        focus_tokens = intent_tokens | kp_tokens

        doc_tokens = [self._doc_tokens(d) for d in ranked_docs]
        doc_scores = [self._score_doc(d, intent_tokens, kp_tokens, kp_text)[0] for d in ranked_docs]

        picked: List[Any] = []
        picked_idx: set[int] = set()
        covered_tokens: set[str] = set()
        per_file_counts: dict[str, int] = defaultdict(int)

        while len(picked) < k and len(picked_idx) < len(ranked_docs):
            best_idx: int | None = None
            best_value: tuple[int, int, int] | None = None

            for i, doc in enumerate(ranked_docs):
                if i in picked_idx:
                    continue
                bucket = self._doc_file_bucket(doc)
                if per_file_counts[bucket] >= max_per_file:
                    continue

                overlap_tokens = doc_tokens[i] & focus_tokens if focus_tokens else set()
                new_tokens = overlap_tokens - covered_tokens
                value = (len(new_tokens), len(overlap_tokens), doc_scores[i])
                if best_value is None or value > best_value:
                    best_value = value
                    best_idx = i

            if best_idx is None:
                break

            chosen = ranked_docs[best_idx]
            picked.append(chosen)
            picked_idx.add(best_idx)
            per_file_counts[self._doc_file_bucket(chosen)] += 1
            if focus_tokens:
                covered_tokens |= (doc_tokens[best_idx] & focus_tokens)

        if len(picked) < k:
            for i, doc in enumerate(ranked_docs):
                if i in picked_idx:
                    continue
                bucket = self._doc_file_bucket(doc)
                if per_file_counts[bucket] >= max_per_file:
                    continue
                picked.append(doc)
                picked_idx.add(i)
                per_file_counts[bucket] += 1
                if len(picked) >= k:
                    break

        if len(picked) < k:
            for i, doc in enumerate(ranked_docs):
                if i in picked_idx:
                    continue
                picked.append(doc)
                if len(picked) >= k:
                    break

        return picked

    def draft(self, payload: KnowledgeDraftPayload | Mapping[str, Any] | str):
        if not isinstance(payload, KnowledgeDraftPayload):
            payload = KnowledgeDraftPayload.model_validate(payload)
        data = payload.model_dump()
        # Optionally enrich external resources using the search RAG manager
        sources_used = []
        retrieval_queries: List[str] = []
        retrieval_query_primary = ""
        retrieval_intent_text = ""
        goal_filters = self._goal_retrieval_filters(data.get("goal_context"))
        if self.use_search and self.search_rag_manager is not None and goal_filters["has_retrieval_fields"]:
            queries, intent_text = self._build_query_bundle(data)
            retrieval_queries = list(queries)
            retrieval_query_primary = queries[0] if queries else ""
            retrieval_intent_text = intent_text
            kp_name = str(self._as_mapping(data.get("knowledge_point")).get("name", "")).strip()
            base_k = max(1, int(getattr(self.search_rag_manager, "max_retrieval_results", 5)))
            # Retrieve more candidates than default, then rerank down to a cleaner final set.
            fetch_k = max(base_k * 3, 12)
            final_k = min(max(base_k, 4), 5)
            extracted_course_codes = self._extract_course_codes(intent_text)
            if goal_filters["course_code"]:
                course_codes = [goal_filters["course_code"]]
            else:
                course_codes = extracted_course_codes
            primary_course_code = goal_filters["course_code"] or (course_codes[0] if course_codes else None)
            lecture_numbers = goal_filters["lecture_numbers"]
            content_category = goal_filters["content_category"]
            page_number = goal_filters["page_number"]
            lecture_intent = (
                bool(lecture_numbers)
                or (content_category or "").lower() == "lectures"
                or ("lecture" in intent_text.lower())
            )

            candidates = []
            seen = set()
            for q in queries:
                docs = []
                if lecture_numbers:
                    for lecture_number in lecture_numbers:
                        docs.extend(
                            self.search_rag_manager.invoke_hybrid_filtered(
                                q,
                                k=fetch_k,
                                course_code=primary_course_code,
                                content_category=content_category or ("Lectures" if lecture_intent else None),
                                lecture_number=lecture_number,
                                page_number=page_number,
                                exclude_file_names=["syllabus.json"] if lecture_intent else None,
                                require_lecture=lecture_intent,
                                allow_web_fallback=False,
                            )
                        )
                else:
                    docs = self.search_rag_manager.invoke_hybrid_filtered(
                        q,
                        k=fetch_k,
                        course_code=primary_course_code,
                        content_category=content_category or ("Lectures" if lecture_intent else None),
                        lecture_number=None,
                        page_number=page_number,
                        exclude_file_names=["syllabus.json"] if lecture_intent else None,
                        require_lecture=lecture_intent,
                        allow_web_fallback=False,
                    )
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

            # If metadata-constrained retrieval is too restrictive, fall back to
            # hybrid retrieval so we can still surface high-signal verified sources.
            if not candidates:
                for q in queries:
                    fallback_docs = self.search_rag_manager.invoke_hybrid(q, k=fetch_k)
                    for d in fallback_docs:
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
            # Require stronger lexical overlap with intent to reduce off-topic chunks.
            strong = [d for d in filtered if self._doc_overlap(d, intent_tokens) >= 3]
            if strong:
                filtered = strong
            else:
                medium = [d for d in filtered if self._doc_overlap(d, intent_tokens) >= 2]
                if medium:
                    filtered = medium
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

            ranked_docs = self._rank_docs(pool, intent_text, kp_name)
            docs = self._select_coverage_diverse_docs(
                ranked_docs,
                final_k,
                intent_text=intent_text,
                kp_text=kp_name,
                max_per_file=2,
            )
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
        if retrieval_queries:
            result["retrieval_query_primary"] = retrieval_query_primary
            result["retrieval_queries"] = retrieval_queries
            result["retrieval_intent_text"] = retrieval_intent_text
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
    session_adaptation_contract: Optional[Mapping[str, Any]] = None,
    lightweight_llm: Any = None,
    max_revision_passes: int = 1,
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
    goal_context: Optional[Mapping[str, Any]] = None,
):
    """Draft a single knowledge point using the agent, optionally enriching with a SearchRagManager."""
    drafter = SearchEnhancedKnowledgeDrafter(llm, search_rag_manager=search_rag_manager, use_search=use_search)
    if session_adaptation_contract is None:
        session_adaptation_contract = build_session_adaptation_contract(learning_session, learner_profile)
    payload = {
        "learner_profile": learner_profile,
        "learning_path": learning_path,
        "learning_session": learning_session,
        "knowledge_points": knowledge_points,
        "knowledge_point": knowledge_point,
        "goal_context": goal_context,
        "visual_formatting_hints": visual_formatting_hints,
        "processing_perception_hints": processing_perception_hints,
        "session_adaptation_contract": format_session_adaptation_contract(session_adaptation_contract),
        "evaluator_feedback": "",
    }

    evaluator_model = lightweight_llm or llm
    evaluation_history: List[dict[str, Any]] = []
    result: dict[str, Any] = {}

    for attempt in range(max(0, int(max_revision_passes)) + 1):
        result = drafter.draft(payload)
        # Post-process: render diagram code blocks to SVG static files
        try:
            from .diagram_renderer import render_diagrams_in_markdown
            if result.get("content"):
                result["content"] = render_diagrams_in_markdown(result["content"])
        except Exception:
            pass   # never break drafting due to diagram rendering failure

        deterministic_eval = deterministic_knowledge_draft_audit(result)
        evaluation = deterministic_eval
        if deterministic_eval.get("is_acceptable", False):
            try:
                evaluation = evaluate_knowledge_draft_with_llm(
                    evaluator_model,
                    learner_profile=learner_profile if isinstance(learner_profile, Mapping) else {},
                    learning_session=learning_session if isinstance(learning_session, Mapping) else {},
                    knowledge_point=knowledge_point if isinstance(knowledge_point, Mapping) else {},
                    knowledge_draft=result,
                    session_adaptation_contract=payload["session_adaptation_contract"],
                )
            except Exception:
                evaluation = deterministic_eval

        evaluation_history.append(evaluation)
        if evaluation.get("is_acceptable", True) or attempt >= max_revision_passes:
            break
        payload["evaluator_feedback"] = str(evaluation.get("improvement_directives", "") or "").strip()

    if evaluation_history:
        result["draft_quality_evaluation"] = evaluation_history[-1]
        if len(evaluation_history) > 1:
            result["draft_quality_evaluation_history"] = evaluation_history
    return result


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
    session_adaptation_contract: Optional[Mapping[str, Any]] = None,
    lightweight_llm: Any = None,
    max_revision_passes: int = 1,
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
    goal_context: Optional[Mapping[str, Any]] = None,
):
    """Draft multiple knowledge points in parallel or sequentially using the agent."""
    if isinstance(learning_session, str):
        learning_session = ast.literal_eval(learning_session)
    if isinstance(knowledge_points, str):
        knowledge_points = ast.literal_eval(knowledge_points)
    if session_adaptation_contract is None:
        session_adaptation_contract = build_session_adaptation_contract(learning_session, learner_profile)
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
            goal_context=goal_context,
            use_search=use_search,
            visual_formatting_hints=visual_formatting_hints,
            processing_perception_hints=processing_perception_hints,
            session_adaptation_contract=session_adaptation_contract,
            lightweight_llm=lightweight_llm,
            max_revision_passes=max_revision_passes,
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
