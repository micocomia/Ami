from __future__ import annotations

import json
from typing import Any, Mapping, MutableMapping, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from base.search_rag import SearchRagManager
from modules.content_generator.agents.media_relevance_evaluator import (
    filter_media_resources_with_llm,
)
from modules.content_generator.utils import find_media_resources
from .common import _record_tool_call


class SearchMediaResourcesInput(BaseModel):
    query: str = Field(..., description="Topic to search media resources for.")
    session_title: str = Field(default="", description="Optional current session title.")
    max_videos: int = Field(default=2, ge=0, le=5)
    max_images: int = Field(default=2, ge=0, le=5)
    max_audio: int = Field(default=1, ge=0, le=5)


def create_search_media_resources_tool(
    *,
    search_rag_manager: Optional[SearchRagManager],
    llm: Any = None,
    enable_llm_filter: bool = True,
    sink: Optional[MutableMapping[str, Any]] = None,
):
    @tool("search_media_resources", args_schema=SearchMediaResourcesInput)
    def search_media_resources(
        query: str,
        session_title: str = "",
        max_videos: int = 2,
        max_images: int = 2,
        max_audio: int = 1,
    ) -> str:
        """Search media resources (video/image/audio) relevant to a tutoring topic."""
        if search_rag_manager is None or search_rag_manager.search_runner is None:
            _record_tool_call(
                sink,
                tool_name="search_media_resources",
                query=query,
                status="unavailable",
                extra={
                    "session_title": session_title,
                    "max_videos": max_videos,
                    "max_images": max_images,
                    "max_audio": max_audio,
                },
            )
            return json.dumps({"media_resources": [], "message": "Media search unavailable."})

        knowledge_points = [{"name": query}]
        try:
            resources = find_media_resources(
                search_rag_manager.search_runner,
                knowledge_points,
                max_videos=max_videos,
                max_images=max_images,
                max_audio=max_audio,
                session_context=session_title or "",
                video_focus="visual",
            )
        except Exception as exc:
            _record_tool_call(
                sink,
                tool_name="search_media_resources",
                query=query,
                status="error",
                extra={
                    "session_title": session_title,
                    "max_videos": max_videos,
                    "max_images": max_images,
                    "max_audio": max_audio,
                    "error": str(exc),
                },
            )
            return json.dumps({"media_resources": [], "message": f"Media search failed: {exc}"})

        if resources and enable_llm_filter and llm is not None:
            try:
                resources = filter_media_resources_with_llm(
                    llm,
                    resources,
                    session_title=session_title or query,
                    knowledge_point_names=[query],
                )
            except Exception:
                pass

        normalized = []
        for item in resources[:8]:
            if not isinstance(item, Mapping):
                continue
            normalized.append({
                "type": str(item.get("type", "")),
                "title": str(item.get("display_title") or item.get("title") or "Learning Resource"),
                "url": str(item.get("url", "")),
                "description": str(item.get("short_description") or item.get("snippet") or item.get("description") or ""),
                "image_url": str(item.get("image_url", "")),
                "thumbnail_url": str(item.get("thumbnail_url", "")),
                "audio_url": str(item.get("audio_url", "")),
                "source": str(item.get("source", "")),
            })
        _record_tool_call(
            sink,
            tool_name="search_media_resources",
            query=query,
            status="ok" if normalized else "empty",
            result_count=len(normalized),
            extra={
                "session_title": session_title,
                "max_videos": max_videos,
                "max_images": max_images,
                "max_audio": max_audio,
            },
        )
        return json.dumps({"media_resources": normalized}, ensure_ascii=False)

    return search_media_resources


__all__ = ["SearchMediaResourcesInput", "create_search_media_resources_tool"]
