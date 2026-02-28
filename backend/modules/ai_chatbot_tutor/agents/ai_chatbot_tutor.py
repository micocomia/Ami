from __future__ import annotations

import ast
import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from pydantic import BaseModel, field_validator

from base import BaseAgent
from base.search_rag import SearchRagManager, format_docs
from modules.ai_chatbot_tutor.prompts.ai_chatbot_tutor import (
    ai_tutor_chatbot_system_prompt,
    ai_tutor_chatbot_task_prompt,
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
        return result


def chat_with_tutor_with_llm(
    llm: Any,
    messages: Optional[Sequence[Mapping[str, Any]]] | str = None,
    learner_profile: Any = "",
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
    safe_preference_update_fn: Optional[Callable[..., Dict[str, Any]]] = None,
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
