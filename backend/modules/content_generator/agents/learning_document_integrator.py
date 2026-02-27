from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from pydantic import BaseModel, field_validator

from base import BaseAgent
from ..prompts.learning_document_integrator import integrated_document_generator_system_prompt, integrated_document_generator_task_prompt
from ..schemas import DocumentStructure
from ..utils import build_session_adaptation_contract, format_session_adaptation_contract


logger = logging.getLogger(__name__)


class IntegratedDocPayload(BaseModel):
    learner_profile: Any
    learning_path: Any
    learning_session: Any
    knowledge_points: Any
    knowledge_drafts: Any
    session_adaptation_contract: Any = ""
    understanding_hints: str = ""

    @field_validator(
        "learner_profile",
        "learning_path",
        "learning_session",
        "knowledge_points",
        "knowledge_drafts",
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

class LearningDocumentIntegrator(BaseAgent):
    name: str = "LearningDocumentIntegrator"

    def __init__(self, model: Any):
        super().__init__(model=model, system_prompt=integrated_document_generator_system_prompt, jsonalize_output=True)

    def integrate(self, payload: IntegratedDocPayload | Mapping[str, Any] | str):
        if not isinstance(payload, IntegratedDocPayload):
            payload = IntegratedDocPayload.model_validate(payload)
        raw_output = self.invoke(payload.model_dump(), task_prompt=integrated_document_generator_task_prompt)
        validated_output = DocumentStructure.model_validate(raw_output)
        return validated_output.model_dump()


def integrate_learning_document_with_llm(
    llm,
    learner_profile,
    learning_path,
    learning_session,
    knowledge_points,
    knowledge_drafts,
    output_markdown=True,
    media_resources: Optional[List[dict]] = None,
    narrative_resources: Optional[List[dict]] = None,
    inline_assets_plan: Optional[List[dict]] = None,
    session_adaptation_contract: Optional[Mapping[str, Any]] = None,
    understanding_hints: str = "",
):
    logger.info(f'Integrating learning document with {len(knowledge_points)} knowledge points and {len(knowledge_drafts)} drafts...')
    if session_adaptation_contract is None:
        session_adaptation_contract = build_session_adaptation_contract(learning_session, learner_profile)
    input_dict = {
        'learner_profile': learner_profile,
        'learning_path': learning_path,
        'learning_session': learning_session,
        'knowledge_points': knowledge_points,
        'knowledge_drafts': knowledge_drafts,
        'session_adaptation_contract': format_session_adaptation_contract(session_adaptation_contract),
        'understanding_hints': understanding_hints,
    }
    learning_document_integrator = LearningDocumentIntegrator(llm)
    document_structure = learning_document_integrator.integrate(input_dict)
    if not output_markdown:
        return document_structure
    logger.info('Preparing markdown document...')
    return prepare_markdown_document(
        document_structure,
        knowledge_points,
        knowledge_drafts,
        media_resources=media_resources,
        narrative_resources=narrative_resources,
        inline_assets_plan=inline_assets_plan,
    )


def _tokenize(text: str) -> set[str]:
    tokens = {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}
    expanded = set(tokens)
    # lightweight singularization improves keyword matching: loops -> loop
    for t in tokens:
        if t.endswith("s") and len(t) > 3:
            expanded.add(t[:-1])
    return expanded


def _asset_text(asset: dict) -> str:
    return " ".join(
        str(asset.get(k, ""))
        for k in ("title", "snippet", "description", "content")
        if asset.get(k)
    )


def build_inline_assets_plan(
    knowledge_points,
    knowledge_drafts,
    media_resources: Optional[List[dict]] = None,
    narrative_resources: Optional[List[dict]] = None,
    max_assets_per_subsection: int = 2,
) -> Tuple[List[dict], Dict[str, Any]]:
    """Build deterministic inline placement for adaptive assets by section index."""
    if not isinstance(knowledge_points, list):
        knowledge_points = []
    if not isinstance(knowledge_drafts, list):
        knowledge_drafts = []
    media_resources = media_resources or []
    narrative_resources = narrative_resources or []

    section_tokens: Dict[int, set[str]] = {}
    section_count = max(len(knowledge_points), len(knowledge_drafts))
    for i in range(section_count):
        kp_name = ""
        kd_title = ""
        if i < len(knowledge_points) and isinstance(knowledge_points[i], dict):
            kp_name = str(knowledge_points[i].get("name", ""))
        if i < len(knowledge_drafts) and isinstance(knowledge_drafts[i], dict):
            kd_title = str(knowledge_drafts[i].get("title", ""))
        section_tokens[i] = _tokenize(f"{kp_name} {kd_title}")

    combined_assets: List[dict] = []
    # Prefer pedagogical narrative inserts when subsection density cap is reached.
    for a in narrative_resources:
        if isinstance(a, dict):
            combined_assets.append({**a, "asset_type": a.get("type", "short_story")})
    for a in media_resources:
        if isinstance(a, dict):
            combined_assets.append({**a, "asset_type": a.get("type", "media")})

    per_section_counts: Dict[int, int] = {i: 0 for i in range(section_count)}
    plan: List[dict] = []
    matched_count = 0
    fallback_count = 0

    for idx, asset in enumerate(combined_assets):
        explicit_idx = asset.get("target_section_index")
        target_idx = explicit_idx if isinstance(explicit_idx, int) else None
        rationale = "explicit_target"

        if target_idx is None or target_idx < 0 or target_idx >= section_count:
            asset_tokens = _tokenize(_asset_text(asset))
            best_score = 0
            best_idx = None
            for sec_idx, toks in section_tokens.items():
                if not toks or not asset_tokens:
                    continue
                score = len(asset_tokens.intersection(toks))
                if score > best_score:
                    best_score = score
                    best_idx = sec_idx
            if best_idx is not None and best_score > 0:
                target_idx = best_idx
                matched_count += 1
                rationale = "keyword_match"
            elif section_count > 0:
                target_idx = idx % section_count
                fallback_count += 1
                rationale = "round_robin_fallback"
            else:
                continue

        if section_count > 0 and per_section_counts[target_idx] >= max_assets_per_subsection:
            placed = False
            for step in range(1, section_count + 1):
                probe = (target_idx + step) % section_count
                if per_section_counts[probe] < max_assets_per_subsection:
                    target_idx = probe
                    rationale = f"{rationale}_density_rollover"
                    placed = True
                    break
            if not placed:
                continue

        per_section_counts[target_idx] += 1
        item = dict(asset)
        item["target_section_index"] = target_idx
        item["rationale"] = rationale
        plan.append(item)

    stats = {
        "sections": section_count,
        "input_assets": len(combined_assets),
        "placed_assets": len(plan),
        "keyword_matches": matched_count,
        "fallbacks": fallback_count,
        "max_assets_per_subsection": max_assets_per_subsection,
    }
    return plan, stats


def _render_inline_asset(resource: dict) -> str:
    r_type = resource.get("asset_type") or resource.get("type", "")
    r_title = resource.get("title", "Resource")
    if r_type == "video":
        video_id = resource.get("video_id", "")
        url = resource.get("url", f"https://www.youtube.com/watch?v={video_id}")
        thumb_url = resource.get("thumbnail_url", "")
        block = f"\n#### 🎬 {r_title}\n"
        if thumb_url:
            block += f"[![{r_title}]({thumb_url})]({url})\n"
        else:
            watch_label = "Watch on Wikimedia Commons" if resource.get("source") == "wikimedia_commons" else "Watch on YouTube"
            block += f"[{watch_label}]({url})\n"
        return block
    if r_type in ("image", "diagram"):
        url = resource.get("url", "")
        image_url = resource.get("image_url", "")
        description = resource.get("description", "")
        icon = "🧩" if r_type == "diagram" else "🖼️"
        block = f"\n#### {icon} {r_title}\n"
        if image_url:
            block += f"[![{r_title}]({image_url})]({url})\n"
        elif url:
            block += f"[View resource]({url})\n"
        if description:
            block += f"*{description}*\n"
        return block
    if r_type == "audio":
        audio_url = resource.get("audio_url", "")
        url = resource.get("url", "")
        block = f"\n#### 🔊 {r_title}\n"
        if audio_url:
            block += f'<audio controls src="{audio_url}"></audio>\n'
        if url:
            block += f"[View source]({url})\n"
        return block
    if r_type in ("short_story", "poem"):
        icon = "📖" if r_type == "short_story" else "✍️"
        label = "Short Story" if r_type == "short_story" else "Poem"
        content = resource.get("content", "")
        audio_url = resource.get("audio_url", "")
        block = f"\n#### {icon} {label}: {r_title}\n\n{content}\n"
        if audio_url:
            block += f'\n<audio controls src="{audio_url}"></audio>\n'
        return block
    return ""


def _sequential_section_body(knowledge_drafts) -> str:
    body_parts: List[str] = []
    for idx, draft in enumerate(knowledge_drafts or []):
        if not isinstance(draft, dict):
            continue
        title = str(draft.get("title") or f"Section {idx + 1}").strip()
        content = str(draft.get("content") or "").strip()
        body_parts.append(f"## {title}\n\n{content}")
    return "\n\n".join(body_parts).strip()


def _canonical_body(document_structure, knowledge_points, knowledge_drafts) -> str:
    content = str(document_structure.get("content", "") or "").strip() if isinstance(document_structure, dict) else ""
    if content:
        if re.search(r"^##\s+", content, re.MULTILINE):
            return content
        return _sequential_section_body(knowledge_drafts)
    return _sequential_section_body(knowledge_drafts)


def _inject_assets_into_body(body: str, inline_by_section: Dict[int, List[dict]]) -> str:
    if not body.strip() or not inline_by_section:
        return body
    matches = list(re.finditer(r"^##\s+.+$", body, re.MULTILINE))
    if not matches:
        return body

    sections: List[str] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        section_text = body[start:end].rstrip()
        asset_blocks = "".join(_render_inline_asset(asset) for asset in inline_by_section.get(idx, []))
        if asset_blocks:
            section_text = f"{section_text}\n{asset_blocks}".rstrip()
        sections.append(section_text)

    extras: List[dict] = []
    for idx, assets in inline_by_section.items():
        if idx >= len(matches):
            extras.extend(assets)
    if extras:
        extra_block = "".join(_render_inline_asset(asset) for asset in extras)
        if extra_block:
            sections.append(f"## Additional Learning Resources\n{extra_block}".rstrip())
    return "\n\n".join(sections).strip()


def prepare_markdown_document(
    document_structure,
    knowledge_points,
    knowledge_drafts,
    media_resources: Optional[List[dict]] = None,
    narrative_resources: Optional[List[dict]] = None,
    inline_assets_plan: Optional[List[dict]] = None,
):
    """Render a markdown learning document from the integrated structure and drafts.

    Expects document_structure with keys: title, overview, summary.
    knowledge_points: list with items containing 'type' in {'foundational','practical','strategic'}.
    knowledge_drafts: list aligned with knowledge_points, each with 'title' and 'content'.
    """
    import ast as _ast
    if isinstance(knowledge_points, str):
        try:
            knowledge_points = _ast.literal_eval(knowledge_points)
        except Exception:
            pass
    if isinstance(knowledge_drafts, str):
        try:
            knowledge_drafts = _ast.literal_eval(knowledge_drafts)
        except Exception:
            pass
    if isinstance(document_structure, str):
        try:
            document_structure = _ast.literal_eval(document_structure)
        except Exception:
            pass

    if not isinstance(document_structure, dict):
        document_structure = {}
    if not isinstance(knowledge_points, list):
        knowledge_points = []
    if not isinstance(knowledge_drafts, list):
        knowledge_drafts = []

    if inline_assets_plan is None:
        inline_assets_plan, _ = build_inline_assets_plan(
            knowledge_points=knowledge_points,
            knowledge_drafts=knowledge_drafts,
            media_resources=media_resources,
            narrative_resources=narrative_resources,
        )
    inline_by_section: Dict[int, List[dict]] = {}
    for item in inline_assets_plan or []:
        sec_idx = item.get("target_section_index")
        if isinstance(sec_idx, int):
            inline_by_section.setdefault(sec_idx, []).append(item)

    title = document_structure.get('title', '') if isinstance(document_structure, dict) else ''
    md = f"# {title}"
    md += f"\n\n{document_structure.get('overview','') if isinstance(document_structure, dict) else ''}"
    body = _canonical_body(document_structure, knowledge_points, knowledge_drafts)
    body = _inject_assets_into_body(body, inline_by_section)
    if body:
        md += f"\n\n{body}"
    md += f"\n\n## Summary\n\n{document_structure.get('summary','') if isinstance(document_structure, dict) else ''}"

    return md
