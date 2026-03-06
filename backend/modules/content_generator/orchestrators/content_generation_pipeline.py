from __future__ import annotations

import ast
import json
import logging
import re
import time
import uuid
from typing import Any, Callable, Mapping, Optional

from base.search_rag import SearchRagManager
from modules.content_generator.agents.document_quiz_generator import generate_document_quizzes_with_llm
from modules.content_generator.agents.goal_oriented_knowledge_explorer import explore_knowledge_points_with_llm
from modules.content_generator.agents.integrated_document_evaluator import evaluate_integrated_document_with_llm
from modules.content_generator.agents.knowledge_draft_evaluator import (
    deterministic_knowledge_draft_audit,
    evaluate_knowledge_draft_batch_with_llm,
)
from modules.content_generator.agents.learning_document_integrator import (
    build_inline_assets_plan,
    integrate_learning_document_with_llm,
    map_integrated_sections_to_draft_ids,
)
from modules.content_generator.agents.media_relevance_evaluator import filter_media_resources_with_llm
from modules.content_generator.agents.narrative_resource_generator import generate_narrative_resources_with_llm
from modules.content_generator.agents.podcast_style_converter import convert_to_podcast_with_llm
from modules.content_generator.agents.search_enhanced_knowledge_drafter import (
    draft_knowledge_point_with_llm,
    draft_knowledge_points_with_llm,
)
from modules.content_generator.schemas import (
    DraftQualityRecord,
    IntegratedQualityRecord,
    OrchestrationQualityTrace,
)
from modules.content_generator.utils import (
    _FSLSM_MODERATE,
    _FSLSM_STRONG,
    build_session_adaptation_contract,
    collect_sources_used,
    find_media_resources,
    generate_tts_audio,
    get_fslsm_dim,
    get_fslsm_input,
    get_fast_llm,
    narrative_allowance,
    processing_perception_hints,
    understanding_hints,
    visual_formatting_hints,
)

logger = logging.getLogger(__name__)


JSONDict = dict[str, Any]

_MAX_BATCH_DRAFTS = 6
_MAX_BATCH_CHARS = 18_000
_MAX_SINGLE_DRAFT_CHARS = 6_000
_MAX_DRAFT_RETRIES = 1
_MAX_INTEGRATOR_RETRIES = 1
_MAX_SECTION_REDRAFT_ROUNDS = 1
_MAX_QUALITY_ROUNDS = 3
_MIN_ACCEPTABLE_DRAFT_RATIO = 0.7


def _parse_jsonish(value: Any, default: Any):
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            return parsed
        except Exception:
            try:
                parsed = json.loads(value)
                return parsed
            except Exception:
                return default
    return value


def _extract_knowledge_points(raw_value: Any) -> list[dict]:
    """Normalize explorer output into a concrete list of knowledge-point dicts."""
    value = raw_value
    if isinstance(value, str):
        value = _parse_jsonish(value, {})
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump()
        except Exception:
            pass
    if isinstance(value, dict):
        kp = value.get("knowledge_points", [])
        if isinstance(kp, list):
            return [x for x in kp if isinstance(x, dict)]
        return []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return []


def _extract_knowledge_drafts(raw_value: Any) -> list[dict]:
    """Normalize drafter output into a concrete list of draft dicts."""
    value = raw_value
    if isinstance(value, str):
        value = _parse_jsonish(value, [])
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump()
        except Exception:
            pass
    if isinstance(value, dict):
        kd = value.get("knowledge_drafts", [])
        if isinstance(kd, list):
            return [x for x in kd if isinstance(x, dict)]
        return []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return []


def _time_stage(trace: dict[str, Any], stage_name: str):
    class _StageTimer:
        def __enter__(self_inner):
            self_inner.start = time.perf_counter()
            return self_inner

        def __exit__(self_inner, exc_type, exc, tb):
            elapsed_ms = (time.perf_counter() - self_inner.start) * 1000.0
            trace.setdefault("stage_timings_ms", {})[stage_name] = round(elapsed_ms, 2)
            return False

    return _StageTimer()


def _draft_is_acceptable(record: dict[str, Any]) -> bool:
    return bool(record.get("deterministic_pass")) and bool(record.get("llm_pass", True))


def _truncate_draft_for_eval(content: str) -> str:
    text = str(content or "")
    if len(text) <= _MAX_SINGLE_DRAFT_CHARS:
        return text
    suffix = "\n\n[...truncated for evaluator context...]\n"
    budget = max(1, _MAX_SINGLE_DRAFT_CHARS - len(suffix))
    return text[:budget] + suffix


def _build_draft_batches(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current_batch: list[dict[str, Any]] = []
    current_chars = 0
    for record in records:
        snapshot = _truncate_draft_for_eval(str(record.get("draft", {}).get("content", "") or ""))
        snapshot_chars = len(snapshot)
        needs_new_batch = (
            len(current_batch) >= _MAX_BATCH_DRAFTS
            or current_chars + snapshot_chars > _MAX_BATCH_CHARS
        )
        if current_batch and needs_new_batch:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0
        current_batch.append(record)
        current_chars += snapshot_chars
    if current_batch:
        batches.append(current_batch)
    return batches


def _required_core_draft_ids(records: list[dict[str, Any]]) -> set[str]:
    foundational = {
        str(r.get("draft_id"))
        for r in records
        if str((r.get("knowledge_point") or {}).get("role", "")).strip().lower() == "foundational"
    }
    if foundational:
        return foundational
    if records:
        return {str(records[0].get("draft_id"))}
    return set()


def _fallback_knowledge_points(learning_session: Mapping[str, Any] | Any) -> list[dict[str, str]]:
    session_title = ""
    if isinstance(learning_session, Mapping):
        session_title = str(learning_session.get("title", "")).strip()
    name = session_title or "Session Core Concepts"
    return [
        {
            "name": name,
            "role": "foundational",
            "solo_level": "beginner",
        }
    ]


def _best_effort_shell_draft(knowledge_point: Mapping[str, Any] | None) -> dict[str, str]:
    kp = knowledge_point if isinstance(knowledge_point, Mapping) else {}
    title = str(kp.get("name", "")).strip() or "Session Overview"
    content = (
        f"## {title}\n\n"
        "This section is generated in best-effort mode because one or more upstream quality checks failed. "
        "Use it as a high-level orientation, then validate details with the cited resources."
    )
    return {"title": title, "content": content}


def _extract_integrated_h2_sections(document: str) -> list[dict[str, Any]]:
    content = str(document or "")
    lines = content.splitlines(keepends=True)
    in_code_fence = False
    fence_token = ""
    headings: list[tuple[int, str]] = []
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
            heading_match = re.match(r"^##\s+(.+?)\s*$", line)
            if heading_match:
                headings.append((offset, heading_match.group(1).strip()))
        offset += len(line)

    sections: list[dict[str, Any]] = []
    for idx, (start, title) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(content)
        markdown = content[start:end].strip()
        body = content[start:end].split("\n", 1)[1].strip() if "\n" in content[start:end] else ""
        sections.append(
            {
                "section_index": idx,
                "title": title,
                "markdown": markdown,
                "body": body,
            }
        )
    return sections


def _deterministic_integrated_section_audit(
    document: str,
    *,
    expected_core_sections: int = 0,
) -> dict[str, Any]:
    sections = _extract_integrated_h2_sections(document)
    if not sections:
        return {
            "is_acceptable": False,
            "issues": ["Integrated document has no top-level ## sections."],
            "improvement_directives": "Generate the integrated document with ordered top-level ## sections and instructional prose under each section.",
            "repair_scope": "integrator_only",
            "affected_section_indices": [],
            "severity": "high",
        }

    issues: list[str] = []
    affected_indices: list[int] = []
    structural_mismatch = False
    placeholder_markers = {"tbd", "todo", "coming soon", "placeholder", "n/a", "lorem ipsum"}
    optional_titles = {"summary", "additional learning resources"}
    scaffolding_titles = {"introduction", "overview", "conclusion", "recap", "summary"}

    def _prose_word_count(text: str) -> int:
        cleaned = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", cleaned)
        cleaned = re.sub(r"<audio[^>]*>.*?</audio>", " ", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"<video[^>]*>.*?</video>", " ", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", cleaned)
        cleaned = re.sub(r"^\s*[-*+]\s+.*$", " ", cleaned, flags=re.MULTILINE)
        words = re.findall(r"[A-Za-z]{3,}", cleaned)
        return len(words)

    core_sections = [
        section
        for section in sections
        if str(section.get("title", "")).strip().lower() not in optional_titles
    ]
    if expected_core_sections > 0 and len(core_sections) != expected_core_sections:
        issues.append(
            f"Core section count mismatch: expected {expected_core_sections}, found {len(core_sections)}. "
            "Normalize top-level ## headings to one core section per draft."
        )
        structural_mismatch = True

    for section in core_sections:
        idx = int(section.get("section_index", 0))
        title = str(section.get("title", "")).strip()
        normalized_title = title.lower()
        body = str(section.get("body", "")).strip()

        if normalized_title in scaffolding_titles:
            issues.append(f"Section '{title}' is generic scaffolding and should teach a session-specific concept.")
            affected_indices.append(idx)

        if not body:
            issues.append(f"Section '{title}' is empty.")
            affected_indices.append(idx)
            continue

        normalized_body = re.sub(r"\s+", " ", body).strip().lower()
        if normalized_body in placeholder_markers:
            issues.append(f"Section '{title}' contains placeholder text only.")
            affected_indices.append(idx)
            continue

        has_asset_markup = bool(
            re.search(r"!\[[^\]]*\]\([^)]+\)", body)
            or re.search(r"<audio[^>]*>.*?</audio>", body, flags=re.DOTALL)
            or re.search(r"<video[^>]*>.*?</video>", body, flags=re.DOTALL)
            or re.search(r"^\s*\|.*\|\s*$", body, flags=re.MULTILINE)
            or re.search(r"```", body)
        )
        prose_words = _prose_word_count(body)
        if has_asset_markup and prose_words < 10:
            issues.append(f"Section '{title}' is asset-heavy and lacks instructional prose.")
            affected_indices.append(idx)

    if not issues:
        return {
            "is_acceptable": True,
            "issues": [],
            "improvement_directives": "",
            "repair_scope": "integrator_only",
            "affected_section_indices": [],
            "severity": "low",
        }

    unique_affected = sorted({idx for idx in affected_indices if isinstance(idx, int)})
    if structural_mismatch:
        return {
            "is_acceptable": False,
            "issues": issues,
            "improvement_directives": (
                "Reintegrate with strict heading normalization: keep exactly one core top-level ## section per draft "
                "in draft order, avoid generic scaffolding headings, and keep Summary as a single final section."
            ),
            "repair_scope": "integrator_only",
            "affected_section_indices": [],
            "severity": "high",
        }

    localized_limit = max(1, expected_core_sections // 2) if expected_core_sections > 0 else 2
    if unique_affected and len(unique_affected) <= localized_limit:
        return {
            "is_acceptable": False,
            "issues": issues,
            "improvement_directives": (
                f"Redraft only section indices {unique_affected} with clear instructional prose and "
                "session-specific, non-generic headings."
            ),
            "repair_scope": "section_redraft",
            "affected_section_indices": unique_affected,
            "severity": "medium" if len(unique_affected) <= 2 else "high",
        }

    return {
        "is_acceptable": False,
        "issues": issues,
        "improvement_directives": (
            "Widespread section quality issues detected. Rebuild all draft sections with stronger instructional depth "
            "and aligned section sequencing."
        ),
        "repair_scope": "full_restart_required",
        "affected_section_indices": unique_affected,
        "severity": "high",
    }


def _resolve_draft_ids_from_sections(
    section_to_draft_ids: dict[int, list[str]],
    affected_section_indices: list[int],
) -> list[str]:
    resolved: list[str] = []
    for section_index in affected_section_indices:
        if not isinstance(section_index, int):
            continue
        for draft_id in section_to_draft_ids.get(section_index, []):
            if draft_id and draft_id not in resolved:
                resolved.append(draft_id)
    return resolved


def _integrated_eval_fallback() -> dict[str, Any]:
    return {
        "is_acceptable": False,
        "issues": ["Integrated quality checkpoint unavailable."],
        "improvement_directives": "Reintegrate with clearer section flow and stronger learner-profile fit.",
        "repair_scope": "full_restart_required",
        "affected_section_indices": [],
        "severity": "high",
    }


def _sync_quality_trace_records(trace: dict[str, Any], draft_records: list[dict[str, Any]], integration_records: list[dict[str, Any]]) -> None:
    trace["draft_records"] = [
        DraftQualityRecord(
            draft_id=str(record.get("draft_id")),
            deterministic_pass=bool(record.get("deterministic_pass")),
            llm_pass=record.get("llm_pass"),
            issues=list(record.get("issues", [])),
            directives=str(record.get("directives", "") or ""),
            attempt_count=int(record.get("attempt_count", 1)),
            status=str(record.get("status", "pending")),
        ).model_dump()
        for record in draft_records
    ]
    trace["integration_records"] = [
        IntegratedQualityRecord(
            is_acceptable=bool(record.get("is_acceptable", True)),
            issues=list(record.get("issues", [])),
            directives=str(record.get("directives", "") or ""),
            repair_scope=str(record.get("repair_scope", "integrator_only")),
            affected_section_indices=list(record.get("affected_section_indices", [])),
            attempt_count=int(record.get("attempt_count", 1)),
        ).model_dump()
        for record in integration_records
    ]


def _apply_deterministic_draft_audit(records: list[dict[str, Any]]) -> None:
    for record in records:
        draft = record.get("draft", {}) if isinstance(record.get("draft"), dict) else {}
        evaluation = deterministic_knowledge_draft_audit(draft)
        record["deterministic_pass"] = bool(evaluation.get("is_acceptable", False))
        if not record["deterministic_pass"]:
            record["llm_pass"] = False
            record["issues"] = list(evaluation.get("issues", []))
            record["directives"] = str(evaluation.get("improvement_directives", "") or "")
            record["status"] = "failed_deterministic"
        else:
            record["llm_pass"] = None
            record["issues"] = []
            record["directives"] = ""
            record["status"] = "pending_llm"


def _apply_batched_draft_eval(
    evaluator_model: Any,
    learner_profile: Mapping[str, Any],
    learning_session: Mapping[str, Any],
    session_adaptation_contract: Any,
    records: list[dict[str, Any]],
    trace: dict[str, Any],
) -> None:
    deterministic_pass_records = [r for r in records if r.get("deterministic_pass")]
    if not deterministic_pass_records:
        return

    batches = _build_draft_batches(deterministic_pass_records)
    for batch_index, batch in enumerate(batches):
        payload_drafts = [
            {
                "draft_id": r.get("draft_id"),
                "knowledge_point": r.get("knowledge_point", {}),
                "knowledge_draft": {
                    "title": str((r.get("draft") or {}).get("title", "") or ""),
                    "content": _truncate_draft_for_eval(str((r.get("draft") or {}).get("content", "") or "")),
                },
            }
            for r in batch
        ]
        try:
            result = evaluate_knowledge_draft_batch_with_llm(
                evaluator_model,
                learner_profile=learner_profile if isinstance(learner_profile, Mapping) else {},
                learning_session=learning_session if isinstance(learning_session, Mapping) else {},
                drafts=payload_drafts,
                session_adaptation_contract=session_adaptation_contract,
            )
            items = result.get("evaluations", [])
            by_id = {str(item.get("draft_id")): item for item in items if isinstance(item, dict)}
            for record in batch:
                item = by_id.get(str(record.get("draft_id")))
                if not item:
                    record["llm_pass"] = False
                    record["issues"] = ["Draft evaluator returned no verdict for this draft."]
                    record["directives"] = "Regenerate this draft with complete instructional content."
                    record["status"] = "failed_llm"
                    continue
                is_ok = bool(item.get("is_acceptable", True))
                record["llm_pass"] = is_ok
                record["issues"] = list(item.get("issues", []))
                record["directives"] = str(item.get("improvement_directives", "") or "")
                record["status"] = "accepted" if is_ok else "failed_llm"
        except Exception as exc:
            trace["draft_evaluator_status"] = "degraded"
            logger.warning("Draft batch evaluator failed for batch %s: %s", batch_index, exc)
            for record in batch:
                # Fallback policy: preserve deterministic pass verdict when the evaluator fails.
                record["llm_pass"] = True
                if not record.get("issues"):
                    record["issues"] = []
                record["directives"] = str(record.get("directives", "") or "")
                record["status"] = "accepted_degraded"


def generate_learning_content_with_llm(
    llm: Any,
    learner_profile: Any,
    learning_path: Any,
    learning_session: Any,
    *,
    allow_parallel: bool = True,
    with_quiz: bool = True,
    max_workers: int = 3,
    use_search: bool = True,
    output_markdown: bool = True,
    method_name: str = "ami",
    search_rag_manager: Optional[SearchRagManager] = None,
    quiz_mix_config: Optional[dict] = None,
    goal_context: Optional[Mapping[str, Any]] = None,
    fast_llm: Any = None,
    evaluator: Optional[Callable[[Any, JSONDict], Mapping[str, Any]]] = None,
) -> JSONDict:
    """Unified learning content orchestration pipeline.

    Flow:
    explore -> draft -> strict draft audit/checkpoint -> targeted draft repair ->
    media/narrative enrichment -> integrate -> final quality checkpoint + targeted repair ->
    audio -> quiz
    """
    if method_name != "ami":
        raise ValueError("Unsupported method_name. Expected 'ami'.")

    learner_profile = _parse_jsonish(learner_profile, {})
    learning_path = _parse_jsonish(learning_path, {})
    learning_session = _parse_jsonish(learning_session, {})

    trace: dict[str, Any] = {
        "trace_id": uuid.uuid4().hex,
        "draft_records": [],
        "integration_records": [],
        "draft_evaluator_status": "ok",
        "quality_checkpoint_passed": False,
        "draft_stage_degraded": False,
        "accepted_draft_ratio": 0.0,
        "explorer_terminal_failure": False,
        "stage_timings_ms": {},
        "fallback_mode": None,
        "final_failure_reason": "",
        "severity": "low",
    }
    integration_records: list[dict[str, Any]] = []
    draft_records: list[dict[str, Any]] = []

    _fast_llm = get_fast_llm(llm, fast_llm)
    session_adaptation_contract = build_session_adaptation_contract(learning_session, learner_profile)

    # 1. Explore knowledge points
    with _time_stage(trace, "explore_knowledge_points"):
        try:
            raw_knowledge_points = explore_knowledge_points_with_llm(
                llm,
                learner_profile,
                learning_path,
                learning_session,
                session_adaptation_contract=session_adaptation_contract,
            )
        except Exception as exc:
            logger.warning("Knowledge explorer terminal failure: %s", exc)
            trace["explorer_terminal_failure"] = True
            trace["fallback_mode"] = "best_effort"
            trace["severity"] = "high"
            trace["final_failure_reason"] = f"Explorer terminal failure: {exc}"
            raw_knowledge_points = {"knowledge_points": _fallback_knowledge_points(learning_session)}
    knowledge_points = _extract_knowledge_points(raw_knowledge_points)
    if not knowledge_points:
        trace["explorer_terminal_failure"] = True
        trace["fallback_mode"] = "best_effort"
        trace["severity"] = "high"
        if not trace.get("final_failure_reason"):
            trace["final_failure_reason"] = "Knowledge explorer returned no valid knowledge points."
        knowledge_points = _fallback_knowledge_points(learning_session)

    fslsm_input = get_fslsm_input(learner_profile)
    fslsm_processing = get_fslsm_dim(learner_profile, "fslsm_processing")
    fslsm_perception = get_fslsm_dim(learner_profile, "fslsm_perception")
    fslsm_understanding = get_fslsm_dim(learner_profile, "fslsm_understanding")

    # 2. Draft knowledge points
    with _time_stage(trace, "draft_knowledge_points"):
        raw_knowledge_drafts = draft_knowledge_points_with_llm(
            llm,
            learner_profile,
            learning_path,
            learning_session,
            knowledge_points,
            goal_context=goal_context,
            allow_parallel=allow_parallel,
            use_search=use_search,
            max_workers=max_workers,
            session_adaptation_contract=session_adaptation_contract,
            fast_llm=_fast_llm,
            max_revision_passes=0,
            run_quality_gate=False,
            search_rag_manager=search_rag_manager,
        )
    knowledge_drafts = _extract_knowledge_drafts(raw_knowledge_drafts)

    if len(knowledge_drafts) < len(knowledge_points):
        missing = len(knowledge_points) - len(knowledge_drafts)
        knowledge_drafts.extend({"title": f"Section {len(knowledge_drafts) + i + 1}", "content": ""} for i in range(missing))
    elif len(knowledge_drafts) > len(knowledge_points):
        knowledge_drafts = knowledge_drafts[: len(knowledge_points)]

    for idx, knowledge_point in enumerate(knowledge_points):
        draft = knowledge_drafts[idx] if idx < len(knowledge_drafts) else {"title": "", "content": ""}
        if not isinstance(draft, dict):
            draft = {"title": str(draft), "content": ""}
        draft_records.append(
            {
                "draft_id": f"draft-{idx}",
                "knowledge_point_id": str(knowledge_point.get("id", f"kp-{idx}")),
                "knowledge_point": knowledge_point,
                "draft": draft,
                "deterministic_pass": False,
                "llm_pass": None,
                "issues": [],
                "directives": "",
                "attempt_count": 1,
                "status": "pending",
            }
        )

    # 3. Draft evaluation
    with _time_stage(trace, "draft_deterministic_audit"):
        _apply_deterministic_draft_audit(draft_records)
    with _time_stage(trace, "draft_llm_checkpoint"):
        _apply_batched_draft_eval(
            _fast_llm,
            learner_profile=learner_profile if isinstance(learner_profile, Mapping) else {},
            learning_session=learning_session if isinstance(learning_session, Mapping) else {},
            session_adaptation_contract=session_adaptation_contract,
            records=draft_records,
            trace=trace,
        )

    failed_drafts = [r for r in draft_records if not _draft_is_acceptable(r)]
    if failed_drafts and _MAX_DRAFT_RETRIES > 0:
        # If there are failed drafts, retry creation
        with _time_stage(trace, "draft_targeted_repair"):
            for record in failed_drafts:
                feedback_lines = list(record.get("issues", []))
                directives = str(record.get("directives", "") or "").strip()
                if directives:
                    feedback_lines.append(directives)
                evaluator_feedback = "\n".join(line for line in feedback_lines if line).strip()

                try:
                    revised = draft_knowledge_point_with_llm(
                        llm,
                        learner_profile=learner_profile,
                        learning_path=learning_path,
                        learning_session=learning_session,
                        knowledge_points=knowledge_points,
                        knowledge_point=record.get("knowledge_point", {}),
                        use_search=use_search,
                        session_adaptation_contract=session_adaptation_contract,
                        fast_llm=_fast_llm,
                        max_revision_passes=0,
                        run_quality_gate=False,
                        evaluator_feedback=evaluator_feedback,
                        search_rag_manager=search_rag_manager,
                        goal_context=goal_context,
                    )
                    record["draft"] = revised if isinstance(revised, dict) else {"title": "", "content": str(revised)}
                    record["attempt_count"] = int(record.get("attempt_count", 1)) + 1
                except Exception as exc:
                    logger.warning("Draft targeted repair failed for %s: %s", record.get("draft_id"), exc)
                    existing_issues = list(record.get("issues", []))
                    existing_issues.append(f"Draft repair failed: {exc}")
                    record["issues"] = existing_issues
                    record["status"] = "failed_repair"

        repaired_subset = failed_drafts
        with _time_stage(trace, "draft_repair_audit"):
            _apply_deterministic_draft_audit(repaired_subset)
        with _time_stage(trace, "draft_repair_llm_checkpoint"):
            _apply_batched_draft_eval(
                _fast_llm,
                learner_profile=learner_profile if isinstance(learner_profile, Mapping) else {},
                learning_session=learning_session if isinstance(learning_session, Mapping) else {},
                session_adaptation_contract=session_adaptation_contract,
                records=repaired_subset,
                trace=trace,
            )

    acceptable_drafts = [r for r in draft_records if _draft_is_acceptable(r)]
    required_core_ids = _required_core_draft_ids(draft_records)
    acceptable_ids = {str(r.get("draft_id")) for r in acceptable_drafts}
    has_required_core = required_core_ids.issubset(acceptable_ids)
    acceptable_ratio = (len(acceptable_drafts) / len(draft_records)) if draft_records else 0.0
    trace["accepted_draft_ratio"] = round(acceptable_ratio, 4)
    trace["draft_stage_degraded"] = any(not _draft_is_acceptable(r) for r in draft_records)

    draft_quality_terminal_failure = trace["draft_stage_degraded"]
    if draft_quality_terminal_failure and (acceptable_ratio < _MIN_ACCEPTABLE_DRAFT_RATIO or not has_required_core):
        trace["fallback_mode"] = "best_effort"
        trace["severity"] = "high"
        trace["final_failure_reason"] = (
            f"Draft quality threshold not met (acceptable_ratio={acceptable_ratio:.2f}, required_core_present={has_required_core})."
        )

    selected_draft_records = acceptable_drafts
    selected_knowledge_points = [r.get("knowledge_point", {}) for r in selected_draft_records]
    selected_knowledge_drafts = [r.get("draft", {}) for r in selected_draft_records]
    if not selected_draft_records:
        trace["fallback_mode"] = "best_effort"
        trace["severity"] = "high"
        if not trace.get("final_failure_reason"):
            trace["final_failure_reason"] = "No acceptable drafts available after strict draft gate."
        shell_kp = knowledge_points[0] if knowledge_points else {"name": "Session Overview", "role": "foundational", "solo_level": "beginner"}
        selected_knowledge_points = [shell_kp]
        selected_knowledge_drafts = [_best_effort_shell_draft(shell_kp)]
        selected_draft_records = [
            {
                "draft_id": "draft-shell-0",
                "knowledge_point_id": "kp-shell-0",
                "knowledge_point": shell_kp,
                "draft": selected_knowledge_drafts[0],
                "deterministic_pass": True,
                "llm_pass": True,
                "issues": ["Best-effort synthetic fallback draft."],
                "directives": "",
                "attempt_count": 1,
                "status": "fallback_shell",
            }
        ]

    sources_used = collect_sources_used(selected_knowledge_drafts)

    media_resources = []
    narrative_resources = []
    inline_assets_plan = None
    session_title = learning_session.get("title", "") if isinstance(learning_session, dict) else ""

    max_videos, max_images, max_audio = 0, 0, 0
    if fslsm_input <= -_FSLSM_MODERATE:
        max_videos = 2 if fslsm_input <= -_FSLSM_STRONG else 1
        max_images = 2 if fslsm_input <= -_FSLSM_STRONG else 1
    elif fslsm_input >= _FSLSM_MODERATE:
        max_audio = 2 if fslsm_input >= _FSLSM_STRONG else 1

    if max_videos or max_images or max_audio:
        with _time_stage(trace, "media_retrieval"):
            _search_runner = getattr(search_rag_manager, "search_runner", None) if search_rag_manager else None
            if _search_runner is None:
                try:
                    from config.loader import default_config
                    from base.searcher_factory import SearchRunner

                    _search_runner = SearchRunner.from_config(default_config)
                except Exception:
                    _search_runner = None

            if _search_runner is not None:
                try:
                    media_resources = find_media_resources(
                        _search_runner,
                        selected_knowledge_points,
                        max_videos=max_videos,
                        max_images=max_images,
                        max_audio=max_audio,
                        session_context=session_title,
                        video_focus="audio" if fslsm_input >= _FSLSM_MODERATE else "visual",
                    )
                except Exception:
                    media_resources = []

        if media_resources:
            with _time_stage(trace, "media_relevance_checkpoint"):
                kp_names = [
                    kp.get("name", "") if isinstance(kp, dict) else str(kp)
                    for kp in selected_knowledge_points
                ]
                media_resources = filter_media_resources_with_llm(
                    llm,
                    media_resources,
                    session_title=session_title,
                    knowledge_point_names=kp_names,
                    fast_llm=_fast_llm,
                )

    verbal_narrative_allowance = narrative_allowance(fslsm_input)
    if verbal_narrative_allowance > 0:
        with _time_stage(trace, "narrative_generation"):
            try:
                narrative_resources = generate_narrative_resources_with_llm(
                    llm,
                    selected_knowledge_points,
                    selected_knowledge_drafts,
                    session_title=session_title,
                    max_narratives=verbal_narrative_allowance,
                    include_tts=False,
                    fast_llm=_fast_llm,
                )
            except Exception:
                narrative_resources = []

    if media_resources or narrative_resources:
        with _time_stage(trace, "inline_asset_planning"):
            inline_assets_plan, inline_stats = build_inline_assets_plan(
                knowledge_points=selected_knowledge_points,
                knowledge_drafts=selected_knowledge_drafts,
                media_resources=media_resources,
                narrative_resources=narrative_resources,
                max_assets_per_subsection=2,
            )
    else:
        inline_stats = {"placed_assets": 0}

    def _integrate_document(integration_feedback: str = "") -> str:
        return integrate_learning_document_with_llm(
            llm,
            learner_profile,
            learning_path,
            learning_session,
            selected_knowledge_points,
            selected_knowledge_drafts,
            output_markdown=output_markdown,
            media_resources=media_resources if media_resources else None,
            narrative_resources=narrative_resources if narrative_resources else None,
            inline_assets_plan=inline_assets_plan,
            session_adaptation_contract=session_adaptation_contract,
            integration_feedback=integration_feedback,
        )

    with _time_stage(trace, "integration"):
        learning_document = _integrate_document("")

    section_to_draft_ids = map_integrated_sections_to_draft_ids(learning_document, selected_draft_records)
    quality_rounds = 0
    integrator_retries = 0
    section_redraft_rounds = 0
    final_integration_eval: dict[str, Any] = _integrated_eval_fallback()

    with _time_stage(trace, "final_quality_checkpoint"):
        while quality_rounds < _MAX_QUALITY_ROUNDS:
            quality_rounds += 1
            deterministic_doc_eval = _deterministic_integrated_section_audit(
                learning_document,
                expected_core_sections=len(selected_knowledge_drafts),
            )
            if not deterministic_doc_eval.get("is_acceptable", False):
                final_integration_eval = {
                    "is_acceptable": False,
                    "issues": list(deterministic_doc_eval.get("issues", [])),
                    "improvement_directives": str(
                        deterministic_doc_eval.get(
                            "improvement_directives",
                            "Fix section structure and ensure each core ## section has instructional prose.",
                        )
                        or ""
                    ),
                    "repair_scope": str(deterministic_doc_eval.get("repair_scope", "integrator_only") or "integrator_only"),
                    "affected_section_indices": list(deterministic_doc_eval.get("affected_section_indices", [])),
                    "severity": str(deterministic_doc_eval.get("severity", "high") or "high"),
                }
            else:
                try:
                    final_integration_eval = evaluate_integrated_document_with_llm(
                        _fast_llm,
                        learner_profile=learner_profile if isinstance(learner_profile, Mapping) else {},
                        learning_session=learning_session if isinstance(learning_session, Mapping) else {},
                        knowledge_points=selected_knowledge_points,
                        session_adaptation_contract=session_adaptation_contract,
                        document=learning_document,
                    )
                except Exception:
                    final_integration_eval = _integrated_eval_fallback()

            integration_records.append(
                {
                    "is_acceptable": bool(final_integration_eval.get("is_acceptable", False)),
                    "issues": list(final_integration_eval.get("issues", [])),
                    "directives": str(final_integration_eval.get("improvement_directives", "") or ""),
                    "repair_scope": str(final_integration_eval.get("repair_scope", "integrator_only")),
                    "affected_section_indices": list(final_integration_eval.get("affected_section_indices", [])),
                    "attempt_count": quality_rounds,
                }
            )

            if final_integration_eval.get("is_acceptable", False):
                break

            repair_scope = str(final_integration_eval.get("repair_scope", "integrator_only"))
            directives = str(final_integration_eval.get("improvement_directives", "") or "").strip()
            affected_section_indices = [
                int(x) for x in final_integration_eval.get("affected_section_indices", []) if isinstance(x, int)
            ]

            if repair_scope == "integrator_only" and integrator_retries < _MAX_INTEGRATOR_RETRIES:
                integrator_retries += 1
                learning_document = _integrate_document(directives)
                section_to_draft_ids = map_integrated_sections_to_draft_ids(learning_document, selected_draft_records)
                continue

            if repair_scope == "section_redraft" and section_redraft_rounds < _MAX_SECTION_REDRAFT_ROUNDS:
                section_redraft_rounds += 1
                target_draft_ids = _resolve_draft_ids_from_sections(section_to_draft_ids, affected_section_indices)
                if not target_draft_ids:
                    trace["fallback_mode"] = "best_effort"
                    trace["final_failure_reason"] = "Section redraft requested but no matching draft ids were resolved."
                    trace["severity"] = "high"
                    break

                for record in selected_draft_records:
                    if str(record.get("draft_id")) not in target_draft_ids:
                        continue
                    repair_feedback = directives or "\n".join(final_integration_eval.get("issues", []))
                    try:
                        revised = draft_knowledge_point_with_llm(
                            llm,
                            learner_profile=learner_profile,
                            learning_path=learning_path,
                            learning_session=learning_session,
                            knowledge_points=selected_knowledge_points,
                            knowledge_point=record.get("knowledge_point", {}),
                            use_search=use_search,
                            session_adaptation_contract=session_adaptation_contract,
                            fast_llm=_fast_llm,
                            max_revision_passes=0,
                            run_quality_gate=False,
                            evaluator_feedback=repair_feedback,
                            search_rag_manager=search_rag_manager,
                            goal_context=goal_context,
                        )
                        record["draft"] = revised if isinstance(revised, dict) else {"title": "", "content": str(revised)}
                        record["attempt_count"] = int(record.get("attempt_count", 1)) + 1
                    except Exception as exc:
                        logger.warning("Section redraft failed for %s: %s", record.get("draft_id"), exc)
                        existing_issues = list(record.get("issues", []))
                        existing_issues.append(f"Section redraft failed: {exc}")
                        record["issues"] = existing_issues
                        record["status"] = "failed_section_redraft"

                repaired_subset = [
                    record for record in selected_draft_records if str(record.get("draft_id")) in target_draft_ids
                ]
                _apply_deterministic_draft_audit(repaired_subset)
                _apply_batched_draft_eval(
                    _fast_llm,
                    learner_profile=learner_profile if isinstance(learner_profile, Mapping) else {},
                    learning_session=learning_session if isinstance(learning_session, Mapping) else {},
                    session_adaptation_contract=session_adaptation_contract,
                    records=repaired_subset,
                    trace=trace,
                )

                selected_knowledge_drafts[:] = [r.get("draft", {}) for r in selected_draft_records]
                learning_document = _integrate_document(directives)
                section_to_draft_ids = map_integrated_sections_to_draft_ids(learning_document, selected_draft_records)
                continue

            trace["fallback_mode"] = "best_effort"
            if repair_scope == "full_restart_required":
                trace["final_failure_reason"] = "Final evaluator requested full restart; auto-restart is disabled."
            elif not trace.get("final_failure_reason"):
                trace["final_failure_reason"] = "Quality round budget exhausted."
            trace["severity"] = str(final_integration_eval.get("severity", "high") or "high")
            break

    quality_checkpoint_passed = bool(final_integration_eval.get("is_acceptable", False))
    trace["quality_checkpoint_passed"] = quality_checkpoint_passed
    if not quality_checkpoint_passed:
        trace["fallback_mode"] = "best_effort"
        if not trace.get("final_failure_reason"):
            issues = final_integration_eval.get("issues", [])
            trace["final_failure_reason"] = "; ".join(issues) if issues else "Final quality checkpoint not passed."
        trace["severity"] = str(final_integration_eval.get("severity", trace.get("severity", "high")) or "high")
    elif trace.get("fallback_mode") is None:
        trace["final_failure_reason"] = ""
        trace["severity"] = "low"

    # Selective redraft may have updated draft contents; refresh source references.
    sources_used = collect_sources_used(selected_knowledge_drafts)

    content_format = "standard"
    if fslsm_input <= -_FSLSM_MODERATE:
        content_format = "visual_enhanced"
    elif fslsm_input >= _FSLSM_MODERATE:
        content_format = "audio_enhanced"

    audio_url = None
    audio_mode = None
    if fslsm_input >= _FSLSM_MODERATE:
        with _time_stage(trace, "audio_generation"):
            try:
                tts_source_document = learning_document
                if fslsm_input >= _FSLSM_STRONG:
                    audio_mode = "host_expert_optional"
                    tts_source_document = convert_to_podcast_with_llm(
                        llm,
                        learning_document,
                        learner_profile,
                        mode="full",
                    )
                else:
                    audio_mode = "narration_optional"

                audio_url = generate_tts_audio(tts_source_document)
            except Exception:
                audio_url = None

    learning_content: JSONDict = {
        "document": learning_document,
        "quizzes": {},
        "sources_used": sources_used,
        "content_format": content_format,
        "inline_assets_count": int((inline_stats or {}).get("placed_assets", 0)),
        "inline_assets_placement_stats": inline_stats or {},
    }
    if audio_mode is not None:
        learning_content["audio_mode"] = audio_mode
    if audio_url is not None:
        learning_content["audio_url"] = audio_url

    if with_quiz:
        with _time_stage(trace, "quiz_generation"):
            if quiz_mix_config:
                from utils.quiz_scorer import get_quiz_mix_for_session as _get_quiz_mix

                session_dict = (
                    learning_session
                    if isinstance(learning_session, dict)
                    else (learning_session.model_dump() if hasattr(learning_session, "model_dump") else {})
                )
                mix = _get_quiz_mix(session_dict, quiz_mix_config)
            else:
                mix = {
                    "single_choice_count": 3,
                    "multiple_choice_count": 0,
                    "true_false_count": 0,
                    "short_answer_count": 0,
                    "open_ended_count": 0,
                }

            learning_content["quizzes"] = generate_document_quizzes_with_llm(
                llm,
                learner_profile,
                learning_document,
                single_choice_count=mix.get("single_choice_count", 3),
                multiple_choice_count=mix.get("multiple_choice_count", 0),
                true_false_count=mix.get("true_false_count", 0),
                short_answer_count=mix.get("short_answer_count", 0),
                open_ended_count=mix.get("open_ended_count", 0),
            )

    _sync_quality_trace_records(trace, draft_records, integration_records)
    trace_model = OrchestrationQualityTrace.model_validate(trace)
    draft_pass_count = sum(1 for item in trace_model.draft_records if item.deterministic_pass and (item.llm_pass is not False))
    logger.info(
        "Draft quality checkpoint trace=%s passed=%s/%s evaluator_status=%s",
        trace_model.trace_id,
        draft_pass_count,
        len(trace_model.draft_records),
        trace_model.draft_evaluator_status,
    )
    logger.info(
        "Content generation quality trace=%s quality_checkpoint_passed=%s fallback_mode=%s severity=%s",
        trace_model.trace_id,
        quality_checkpoint_passed,
        trace_model.fallback_mode,
        trace_model.severity,
    )
    logger.info("Content generation stage timings trace=%s timings_ms=%s", trace_model.trace_id, trace_model.stage_timings_ms)
    logger.info("Content generation quality details: %s", json.dumps(trace_model.model_dump(), default=str))

    if evaluator is not None:
        try:
            _ = evaluator(_fast_llm, learning_content)
        except Exception as exc:
            logger.warning("Learning content evaluator hook failed: %s", exc)

    return learning_content
