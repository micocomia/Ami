from __future__ import annotations

import ast
import json
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from pydantic import BaseModel, field_validator

from base import BaseAgent
from base.search_rag import SearchRagManager, format_docs
from modules.ai_chatbot_tutor.prompts.ai_chatbot_tutor import (
    ai_tutor_chatbot_system_prompt,
    ai_tutor_chatbot_task_prompt,
)
from modules.ai_chatbot_tutor.tools.common import (
    _document_to_trace_context,
    _record_contexts,
    _record_tool_call,
)
from modules.ai_chatbot_tutor.tools import create_ai_tutor_tools


def _stringify_history(messages: Any) -> str:
    if messages is None or len(messages) == 0:
        return ""
    if isinstance(messages, str):
        try:
            messages = ast.literal_eval(messages)
        except Exception:
            return messages
    lines: List[str] = []
    for m in list(messages or []):
        if isinstance(m, Mapping):
            role = str(m.get("role", "user"))
            content = str(m.get("content", ""))
        else:
            role = "user"
            content = str(m)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _last_user_query(messages: Any) -> str:
    if messages is None:
        return ""
    if isinstance(messages, str):
        try:
            messages = ast.literal_eval(messages)
        except Exception:
            return messages
    for m in reversed(list(messages or [])):
        if isinstance(m, Mapping) and str(m.get("role", "")).lower() == "user":
            return str(m.get("content", "")).strip()
    if messages:
        last = messages[-1]
        if isinstance(last, Mapping):
            return str(last.get("content", "")).strip()
        return str(last).strip()
    return ""


def _coerce_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, Mapping):
                return dict(parsed)
        except Exception:
            pass
        try:
            parsed = json.loads(text)
            if isinstance(parsed, Mapping):
                return dict(parsed)
        except Exception:
            pass
    return {}


def _extract_fslsm_dims(profile: Any) -> Dict[str, float]:
    profile_map = _coerce_mapping(profile)
    prefs = profile_map.get("learning_preferences", {})
    if not isinstance(prefs, Mapping):
        prefs = {}
    dims = prefs.get("fslsm_dimensions", {})
    if not isinstance(dims, Mapping):
        dims = {}

    out: Dict[str, float] = {
        "fslsm_processing": 0.0,
        "fslsm_perception": 0.0,
        "fslsm_input": 0.0,
        "fslsm_understanding": 0.0,
    }
    for key in list(out.keys()):
        try:
            out[key] = float(dims.get(key, 0.0))
        except Exception:
            out[key] = 0.0
    return out


def _fslsm_adaptation_guidance(profile: Any) -> str:
    dims = _extract_fslsm_dims(profile)
    moderate = 0.3
    lines: List[str] = []

    processing = dims["fslsm_processing"]
    if processing <= -moderate:
        lines.append("- Processing: use active practice prompts and short check-ins.")
    elif processing >= moderate:
        lines.append("- Processing: include reflection pauses before final answers.")
    else:
        lines.append("- Processing: balance explanation and interaction.")

    perception = dims["fslsm_perception"]
    if perception <= -moderate:
        lines.append("- Perception: start with concrete examples, then generalize.")
    elif perception >= moderate:
        lines.append("- Perception: start with conceptual framework, then examples.")
    else:
        lines.append("- Perception: mix conceptual and concrete explanations.")

    input_dim = dims["fslsm_input"]
    if input_dim <= -moderate:
        lines.append("- Input: prefer visual descriptions, diagrams/charts, and structured bullet layouts.")
    elif input_dim >= moderate:
        lines.append("- Input: prefer verbal/written explanations and narrative clarity.")
    else:
        lines.append("- Input: keep a mixed presentation style.")

    understanding = dims["fslsm_understanding"]
    if understanding <= -moderate:
        lines.append("- Understanding: explain step-by-step in a sequential order.")
    elif understanding >= moderate:
        lines.append("- Understanding: provide big-picture overview first, then details.")
    else:
        lines.append("- Understanding: combine overview and sequence.")

    lines.append(f"- FSLSM raw dimensions: {dims}")
    return "\n".join(lines)


def _goal_scope_text(profile: Any) -> str:
    profile_map = _coerce_mapping(profile)
    goal = str(profile_map.get("learning_goal", "") or profile_map.get("goal", "")).strip()
    if not goal:
        return "No explicit learning goal found in profile."
    return goal


def _goal_context_text(goal_context: Any) -> str:
    goal_context_map = _coerce_mapping(goal_context)
    if not goal_context_map:
        return "No structured goal context provided."
    return json.dumps(goal_context_map, indent=2, sort_keys=True)


def _guardrail_policy_text() -> str:
    return (
        "- Never claim to execute filesystem or admin actions.\n"
        "- Refuse destructive/system requests (e.g., deleting backend files).\n"
        "- If the question is outside the learner's current goal, explicitly say so and redirect.\n"
        "- If evidence/context is insufficient, say that clearly and ask for missing context."
    )


class TutorChatPayload(BaseModel):
    learner_profile: Any = ""
    messages: Any
    use_search: bool = True
    top_k: int = 5
    external_resources: Optional[str] = None
    goal_context: Optional[Any] = None

    # New additive fields
    user_id: Optional[str] = None
    goal_id: Optional[int] = None
    session_index: Optional[int] = None
    use_vector_retrieval: Optional[bool] = None
    use_web_search: Optional[bool] = None
    use_media_search: Optional[bool] = None
    allow_preference_updates: bool = True
    return_metadata: bool = False
    learner_information: Optional[str] = ""

    @field_validator("learner_profile")
    @classmethod
    def coerce_profile(cls, v: Any) -> Any:
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, Mapping):
            return dict(v)
        return v


class AITutorChatbot(BaseAgent):
    name: str = "AITutorChatbot"
    _NOISE_TOKENS = {
        "lecture", "lectures", "course", "courses", "today", "welcome",
        "download", "slides", "files", "follow", "along", "introduction",
        "information", "terms", "use", "ocw", "mit", "python", "fall",
    }
    _QUERY_STOPWORDS = {
        "using", "explain", "teach", "focus", "overview", "topic", "topics",
        "knowledge", "point", "points", "material", "materials", "session",
        "goal", "learn", "learning", "content", "beginner", "basics",
        "style", "with", "from", "into", "about",
    }
    _GENERIC_CHUNK_MARKERS = (
        "overview of course",
        "what do computer scientists do",
        "hope we have started you down the path",
        "download slides and .py files and follow along",
        "for information about citing these materials",
    )

    def __init__(
        self,
        model: Any,
        *,
        search_rag_manager: Optional[SearchRagManager] = None,
        safe_preference_update_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    ):
        super().__init__(
            model=model,
            system_prompt=ai_tutor_chatbot_system_prompt,
            tools=None,
            jsonalize_output=False,
        )
        self.search_rag_manager = search_rag_manager
        self.safe_preference_update_fn = safe_preference_update_fn

    def _resolve_tool_toggles(self, data: Dict[str, Any]) -> Dict[str, bool]:
        # Legacy semantics: use_search=True previously meant web+retrieval path.
        legacy_use_search = bool(data.get("use_search", True))
        use_web_search = data.get("use_web_search")
        use_vector_retrieval = data.get("use_vector_retrieval")
        use_media_search = data.get("use_media_search")

        if use_web_search is None:
            use_web_search = legacy_use_search
        if use_vector_retrieval is None:
            use_vector_retrieval = not legacy_use_search
        if use_media_search is None:
            use_media_search = True

        return {
            "use_web_search": bool(use_web_search),
            "use_vector_retrieval": bool(use_vector_retrieval),
            "use_media_search": bool(use_media_search),
            "allow_preference_updates": bool(data.get("allow_preference_updates", True)),
        }

    def _build_runtime_tools(self, data: Dict[str, Any], sink: Dict[str, Any]) -> List[Any]:
        toggles = self._resolve_tool_toggles(data)
        return create_ai_tutor_tools(
            search_rag_manager=self.search_rag_manager,
            llm=self._model,
            safe_preference_update_fn=self.safe_preference_update_fn,
            preference_update_sink=sink,
            enable_session_content=True,
            enable_vector_retrieval=toggles["use_vector_retrieval"],
            enable_web_search=toggles["use_web_search"],
            enable_media_search=toggles["use_media_search"],
            enable_preference_updates=toggles["allow_preference_updates"],
        )

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

    def _goal_retrieval_filters(self, value: Any) -> Dict[str, Any]:
        ctx = _coerce_mapping(value)
        course_code = str(ctx.get("course_code") or "").strip() or None
        content_category = str(ctx.get("content_category") or "").strip() or None
        page_number = ctx.get("page_number")
        if not isinstance(page_number, int) or page_number <= 0:
            page_number = None
        lecture_numbers = self._normalize_lecture_numbers(ctx.get("lecture_numbers", ctx.get("lecture_number")))
        return {
            "course_code": course_code,
            "content_category": content_category,
            "page_number": page_number,
            "lecture_numbers": lecture_numbers,
            "has_retrieval_fields": any([course_code, content_category, page_number, lecture_numbers]),
        }

    def _prefetch_goal_context_retrieval(
        self,
        *,
        data: Dict[str, Any],
        query: str,
        sink: Dict[str, Any],
        external_context: str,
    ) -> str:
        toggles = self._resolve_tool_toggles(data)
        goal_filters = self._goal_retrieval_filters(data.get("goal_context"))
        if (
            not toggles["use_vector_retrieval"]
            or self.search_rag_manager is None
            or not goal_filters["has_retrieval_fields"]
            or not query
        ):
            return external_context

        top_k = max(1, min(int(data.get("top_k", 5) or 5), 5))
        fetch_k = min(max(top_k + 1, 4), 6)
        final_k = top_k
        docs = []
        seen = set()
        lecture_numbers = goal_filters["lecture_numbers"]
        context_tool_name = "prefetch_goal_context_hybrid_filtered"
        goal_context_map = _coerce_mapping(data.get("goal_context"))
        goal_scope = _goal_scope_text(data.get("learner_profile"))
        lecture_intent = bool(lecture_numbers) or (goal_filters["content_category"] or "").lower() == "lectures"

        def _extract_course_codes(*texts: str) -> List[str]:
            pat = re.compile(r"\b\d+\.\d+\b|\b[A-Za-z]+\d{3,}\b|\b\d+[A-Za-z]+\d*\b")
            out: List[str] = []
            for text in texts:
                if not text:
                    continue
                for code in pat.findall(text):
                    if code not in out:
                        out.append(code)
            return out

        def _tokenize(text: str) -> set[str]:
            toks = {
                t for t in re.findall(r"[a-z0-9][a-z0-9\.\-_]+", (text or "").lower())
                if len(t) > 1
            }
            return {
                t for t in toks
                if t not in self._NOISE_TOKENS and t not in self._QUERY_STOPWORDS
            }

        def _doc_tokens(doc: Any) -> set[str]:
            meta = getattr(doc, "metadata", {}) or {}
            meta_text = " ".join([
                str(meta.get("title", "")),
                str(meta.get("course_code", "")),
                str(meta.get("course_name", "")),
                str(meta.get("file_name", "")),
                str(meta.get("content_category", "")),
            ])
            return _tokenize(f"{meta_text} {getattr(doc, 'page_content', '')}")

        def _is_lecture_doc(meta: Mapping[str, Any]) -> bool:
            if meta.get("lecture_number") is not None:
                return True
            category = str(meta.get("content_category", "")).lower().strip()
            if category == "lectures":
                return True
            file_name = str(meta.get("file_name", "")).lower().strip()
            return file_name.startswith("lec_") and file_name.endswith(".pdf")

        def _is_low_signal_text(text: str) -> bool:
            lowered = (text or "").strip().lower()
            if not lowered:
                return True
            if any(marker in lowered for marker in self._GENERIC_CHUNK_MARKERS):
                return True
            if any(marker in lowered for marker in [
                "for information about citing these materials",
                "terms of use",
                "ocw.mit.edu/terms",
            ]):
                return True
            if "download slides and .py files and follow along" in lowered:
                return True
            if lowered.startswith("welcome!"):
                return True
            if "today" in lowered and "course info" in lowered:
                return True
            return sum(1 for ch in lowered if ch.isalpha()) < 40

        def _match_course_code(doc: Any, course_codes: List[str]) -> bool:
            if not course_codes:
                return True
            meta = getattr(doc, "metadata", {}) or {}
            code = str(meta.get("course_code", "")).lower().strip()
            if not code:
                return True
            return code in {c.lower() for c in course_codes}

        def _doc_overlap(doc: Any, intent_tokens: set[str]) -> int:
            return len(intent_tokens & _doc_tokens(doc))

        def _score_doc(doc: Any, intent_tokens: set[str]) -> tuple[int, int]:
            meta = getattr(doc, "metadata", {}) or {}
            source_type = str(meta.get("source_type", "")).lower()
            file_name = str(meta.get("file_name", "")).lower().strip()
            doc_text = (
                f"{' '.join(str(meta.get(k, '')) for k in ['title', 'course_code', 'course_name', 'file_name', 'content_category'])} "
                f"{getattr(doc, 'page_content', '')}"
            ).lower()
            overlap = _doc_overlap(doc, intent_tokens)
            verified_boost = 3 if source_type == "verified_content" else 0
            lecture_boost = 4 if _is_lecture_doc(meta) else 0
            syllabus_penalty = -3 if "syllabus" in file_name else 0
            generic_penalty = -4 if any(marker in doc_text for marker in self._GENERIC_CHUNK_MARKERS) else 0
            low_signal_penalty = -2 if _is_low_signal_text(getattr(doc, "page_content", "")) else 0
            score = overlap * 2 + verified_boost + lecture_boost + syllabus_penalty + generic_penalty + low_signal_penalty
            return score, overlap

        def _doc_file_bucket(doc: Any) -> str:
            meta = getattr(doc, "metadata", {}) or {}
            file_name = str(meta.get("file_name", "")).strip().lower()
            if file_name:
                return file_name
            source = str(meta.get("source", "")).strip().lower()
            return source or "unknown"

        def _select_docs(candidates: Sequence[Any], *, intent_text: str) -> List[Any]:
            if not candidates:
                return []
            course_codes = [goal_filters["course_code"]] if goal_filters["course_code"] else _extract_course_codes(
                query,
                goal_scope,
                json.dumps(goal_context_map, sort_keys=True),
            )
            intent_tokens = _tokenize(intent_text)
            filtered = [
                doc for doc in candidates
                if _match_course_code(doc, course_codes) and not _is_low_signal_text(getattr(doc, "page_content", ""))
            ]
            if lecture_intent:
                lecture_filtered = [doc for doc in filtered if _is_lecture_doc(getattr(doc, "metadata", {}) or {})]
                if lecture_filtered:
                    filtered = lecture_filtered
            strong = [doc for doc in filtered if _doc_overlap(doc, intent_tokens) >= 3]
            if strong:
                filtered = strong
            else:
                medium = [doc for doc in filtered if _doc_overlap(doc, intent_tokens) >= 2]
                if medium:
                    filtered = medium
            if not filtered:
                filtered = [doc for doc in candidates if _match_course_code(doc, course_codes)]
            if not filtered:
                filtered = list(candidates)

            ranked = sorted(filtered, key=lambda doc: _score_doc(doc, intent_tokens), reverse=True)
            picked: List[Any] = []
            picked_idx: set[int] = set()
            per_file_counts: Dict[str, int] = {}
            covered_tokens: set[str] = set()
            doc_tokens = [_doc_tokens(doc) for doc in ranked]
            doc_scores = [_score_doc(doc, intent_tokens)[0] for doc in ranked]

            while len(picked) < final_k and len(picked_idx) < len(ranked):
                best_idx: Optional[int] = None
                best_value: Optional[tuple[int, int, int]] = None
                for idx, doc in enumerate(ranked):
                    if idx in picked_idx:
                        continue
                    bucket = _doc_file_bucket(doc)
                    if per_file_counts.get(bucket, 0) >= 2:
                        continue
                    overlap_tokens = doc_tokens[idx] & intent_tokens if intent_tokens else set()
                    new_tokens = overlap_tokens - covered_tokens
                    value = (len(new_tokens), len(overlap_tokens), doc_scores[idx])
                    if best_value is None or value > best_value:
                        best_value = value
                        best_idx = idx
                if best_idx is None:
                    break
                chosen = ranked[best_idx]
                picked.append(chosen)
                picked_idx.add(best_idx)
                bucket = _doc_file_bucket(chosen)
                per_file_counts[bucket] = per_file_counts.get(bucket, 0) + 1
                covered_tokens |= (doc_tokens[best_idx] & intent_tokens)

            if len(picked) < final_k:
                for idx, doc in enumerate(ranked):
                    if idx in picked_idx:
                        continue
                    bucket = _doc_file_bucket(doc)
                    if per_file_counts.get(bucket, 0) >= 2:
                        continue
                    picked.append(doc)
                    picked_idx.add(idx)
                    per_file_counts[bucket] = per_file_counts.get(bucket, 0) + 1
                    if len(picked) >= final_k:
                        break

            return picked[:final_k]

        def _add_docs(candidates: Sequence[Any]) -> None:
            for doc in candidates or []:
                meta = getattr(doc, "metadata", {}) or {}
                key = (
                    str(meta.get("source_type", "")),
                    str(meta.get("course_code", "")),
                    str(meta.get("file_name", "")),
                    str(meta.get("page_number", "")),
                    str(getattr(doc, "page_content", ""))[:180],
                )
                if key in seen:
                    continue
                seen.add(key)
                docs.append(doc)

        try:
            if lecture_numbers:
                for lecture_number in lecture_numbers:
                    _add_docs(
                        self.search_rag_manager.invoke_hybrid_filtered(
                            query,
                            k=fetch_k,
                            course_code=goal_filters["course_code"],
                            content_category=goal_filters["content_category"] or ("Lectures" if lecture_intent else None),
                            lecture_number=lecture_number,
                            page_number=goal_filters["page_number"],
                            exclude_file_names=["syllabus.json"] if lecture_intent else None,
                            require_lecture=lecture_intent,
                            allow_web_fallback=False,
                        )
                    )
            else:
                _add_docs(
                    self.search_rag_manager.invoke_hybrid_filtered(
                        query,
                        k=fetch_k,
                        course_code=goal_filters["course_code"],
                        content_category=goal_filters["content_category"] or ("Lectures" if lecture_intent else None),
                        lecture_number=None,
                        page_number=goal_filters["page_number"],
                        exclude_file_names=["syllabus.json"] if lecture_intent else None,
                        require_lecture=lecture_intent,
                        allow_web_fallback=False,
                    )
                )
            _record_tool_call(
                sink,
                tool_name="prefetch_goal_context_hybrid_filtered",
                query=query,
                status="ok" if docs else "empty",
                result_count=len(docs),
                extra={"goal_context": _coerce_mapping(data.get("goal_context"))},
            )
        except Exception as exc:
            _record_tool_call(
                sink,
                tool_name="prefetch_goal_context_hybrid_filtered",
                query=query,
                status="error",
                extra={"goal_context": _coerce_mapping(data.get("goal_context")), "error": str(exc)},
            )
            docs = []

        if not docs:
            try:
                fallback_docs = self.search_rag_manager.invoke_hybrid(query, k=fetch_k)
                _add_docs(fallback_docs)
                context_tool_name = "prefetch_goal_context_hybrid"
                _record_tool_call(
                    sink,
                    tool_name="prefetch_goal_context_hybrid",
                    query=query,
                    status="ok" if docs else "empty",
                    result_count=len(docs),
                    extra={"goal_context": _coerce_mapping(data.get("goal_context"))},
                )
            except Exception as exc:
                _record_tool_call(
                    sink,
                    tool_name="prefetch_goal_context_hybrid",
                    query=query,
                    status="error",
                    extra={"goal_context": _coerce_mapping(data.get("goal_context")), "error": str(exc)},
                )

        if not docs:
            return external_context

        intent_text = " ".join(
            value for value in [
                query,
                goal_scope,
                str(goal_filters["content_category"] or "").strip(),
                " ".join(str(n) for n in lecture_numbers),
            ]
            if value
        ).strip()
        docs = _select_docs(docs, intent_text=intent_text) or docs[:final_k]

        _record_contexts(
            sink,
            tool_name=context_tool_name,
            query=query,
            contexts=[_document_to_trace_context(doc) for doc in docs[:final_k]],
        )
        context = format_docs(docs[:final_k])
        if not context:
            return external_context
        return f"{external_context}\n{context}" if external_context else context

    def chat(self, payload: TutorChatPayload | Mapping[str, Any] | str):
        if not isinstance(payload, TutorChatPayload):
            payload = TutorChatPayload.model_validate(payload)

        data = payload.model_dump()
        messages = data.get("messages")
        history_text = _stringify_history(messages)
        query = _last_user_query(messages)

        external_context = data.get("external_resources") or ""
        metadata_sink: Dict[str, Any] = {}
        tools = self._build_runtime_tools(data, metadata_sink)

        # Rebuild the internal agent with runtime tool availability.
        self._tools = tools
        self._agent = self._build_agent()

        external_context = self._prefetch_goal_context_retrieval(
            data=data,
            query=query,
            sink=metadata_sink,
            external_context=external_context,
        )

        # Backward-compatible preloaded context when tools are effectively disabled.
        if not tools and self.search_rag_manager is not None and query:
            try:
                if data.get("use_search", True):
                    docs = self.search_rag_manager.invoke(query)
                else:
                    docs = self.search_rag_manager.retrieve(query, k=max(1, int(data.get("top_k", 5))))
                context = format_docs(docs)
                if context:
                    external_context = f"{external_context}\n{context}" if external_context else context
            except Exception:
                pass

        input_vars = {
            "learner_profile": data.get("learner_profile", ""),
            "learner_information": data.get("learner_information", ""),
            "goal_scope": _goal_scope_text(data.get("learner_profile", "")),
            "goal_context": _goal_context_text(data.get("goal_context")),
            "fslsm_adaptation_guidance": _fslsm_adaptation_guidance(data.get("learner_profile", "")),
            "guardrail_policy": _guardrail_policy_text(),
            "user_id": data.get("user_id"),
            "goal_id": data.get("goal_id"),
            "session_index": data.get("session_index"),
            "messages": history_text,
            "latest_user_message": query,
            "external_resources": external_context,
        }
        raw_reply = self.invoke(input_vars, task_prompt=ai_tutor_chatbot_task_prompt)

        if not data.get("return_metadata", False):
            return raw_reply

        result: Dict[str, Any] = {
            "response": raw_reply,
            "profile_updated": bool(metadata_sink.get("profile_updated", False)),
        }
        updated_profile = metadata_sink.get("updated_learner_profile")
        if isinstance(updated_profile, Mapping):
            result["updated_learner_profile"] = dict(updated_profile)
        retrieval_trace = metadata_sink.get("retrieval_trace")
        if isinstance(retrieval_trace, Mapping):
            cleaned_trace = {
                "contexts": list(retrieval_trace.get("contexts", []) or []),
                "tool_calls": list(retrieval_trace.get("tool_calls", []) or []),
            }
        else:
            cleaned_trace = {"contexts": [], "tool_calls": []}
        result["retrieval_trace"] = cleaned_trace
        return result


def chat_with_tutor_with_llm(
    llm: Any,
    messages: Optional[Sequence[Mapping[str, Any]]] | str = None,
    learner_profile: Any = "",
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
    safe_preference_update_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    goal_context: Optional[Any] = None,
    use_search: bool = True,
    top_k: int = 5,
    user_id: Optional[str] = None,
    goal_id: Optional[int] = None,
    session_index: Optional[int] = None,
    use_vector_retrieval: Optional[bool] = None,
    use_web_search: Optional[bool] = None,
    use_media_search: Optional[bool] = None,
    allow_preference_updates: bool = True,
    learner_information: Optional[str] = "",
    return_metadata: bool = False,
):
    """Run an AI tutor chat turn with optional tool-enabled context.

    Backward compatibility:
    - return_metadata=False (default) -> returns string response
    - return_metadata=True -> returns dict with response + optional metadata
    """
    agent = AITutorChatbot(
        llm,
        search_rag_manager=search_rag_manager,
        safe_preference_update_fn=safe_preference_update_fn,
    )
    payload = {
        "learner_profile": learner_profile,
        "messages": messages,
        "goal_context": goal_context,
        "use_search": use_search,
        "top_k": top_k,
        "user_id": user_id,
        "goal_id": goal_id,
        "session_index": session_index,
        "use_vector_retrieval": use_vector_retrieval,
        "use_web_search": use_web_search,
        "use_media_search": use_media_search,
        "allow_preference_updates": allow_preference_updates,
        "learner_information": learner_information,
        "return_metadata": return_metadata,
    }
    return agent.chat(payload)
