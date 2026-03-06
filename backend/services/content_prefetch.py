import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from modules.content_generator.orchestrators.content_generation_pipeline import ContentGenerationCancelled


class ContentPrefetchService:
    _SESSION_GUARD_EXCLUDED_FIELDS = {
        "mastery_score",
        "is_mastered",
        "mastery_threshold",
    }

    def __init__(
        self,
        *,
        app_config: Dict[str, Any],
        logger: Any,
        store: Any,
        get_llm: Callable[..., Any],
        build_learning_content_payload: Callable[..., Dict[str, Any]],
        path_hash_fn: Callable[[Dict[str, Any]], str],
        current_path_hash_fn: Callable[[str, int], str],
    ) -> None:
        self._app_config = app_config
        self._logger = logger
        self._store = store
        self._get_llm = get_llm
        self._build_learning_content_payload = build_learning_content_payload
        self._path_hash_fn = path_hash_fn
        self._current_path_hash_fn = current_path_hash_fn

        self._lock_guard = threading.Lock()
        self._registry: Dict[str, Dict[str, Any]] = {}
        self._last_trigger_at: Dict[str, float] = {}
        self._futures: Dict[str, Future] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        max_workers = int(self._app_config.get("prefetch_max_workers", 2) or 2)
        self._executor = ThreadPoolExecutor(
            max_workers=max(max_workers, 1),
            thread_name_prefix="content-prefetch",
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def prefetch_enabled(self) -> bool:
        return bool(self._app_config.get("prefetch_enabled", False))

    def prefetch_short_wait_secs(self) -> float:
        return float(self._app_config.get("prefetch_wait_short_secs", 8))

    def prefetch_long_wait_secs(self) -> float:
        return float(self._app_config.get("prefetch_wait_long_secs", 130))

    def prefetch_cooldown_secs(self) -> float:
        return float(self._app_config.get("prefetch_cooldown_secs", 20))

    @staticmethod
    def content_cache_key(user_id: str, goal_id: int, session_index: int) -> str:
        return f"{user_id}:{goal_id}:{session_index}"

    def current_path_hash(self, user_id: str, goal_id: int) -> str:
        return self._current_path_hash_fn(user_id, goal_id)

    def log_content_event(
        self,
        event_name: str,
        *,
        user_id: str,
        goal_id: int,
        session_index: int,
        trigger_source: str,
        status: str,
        path_hash: str,
        duration_ms: float,
        **extra: Any,
    ) -> None:
        payload: Dict[str, Any] = {
            "event": event_name,
            "user_id": user_id,
            "goal_id": goal_id,
            "session_index": session_index,
            "trigger_source": trigger_source,
            "status": status,
            "path_hash": path_hash,
            "duration_ms": round(float(duration_ms), 2),
        }
        payload.update(extra)
        self._logger.info(
            "content-trace %s",
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
        )

    @staticmethod
    def first_unlearned_session_index(
        learning_path: Any,
        *,
        start_after: int = -1,
    ) -> Optional[int]:
        if not isinstance(learning_path, list):
            return None
        start = max(start_after + 1, 0)
        for idx in range(start, len(learning_path)):
            session = learning_path[idx]
            if isinstance(session, dict) and not bool(session.get("if_learned", False)):
                return idx
        return None

    def singleflight_try_start(
        self,
        cache_key: str,
        *,
        path_hash_at_start: str,
        trigger_source: str,
        session_guard_hash_at_start: Optional[str] = None,
    ) -> Optional[str]:
        owner_token = uuid.uuid4().hex
        with self._lock_guard:
            existing = self._registry.get(cache_key)
            if isinstance(existing, dict) and existing.get("status") == "running":
                return None
            self._registry[cache_key] = {
                "status": "running",
                "event": threading.Event(),
                "owner_token": owner_token,
                "path_hash_at_start": path_hash_at_start,
                "session_guard_hash_at_start": session_guard_hash_at_start,
                "started_at": self._now_iso(),
                "finished_at": None,
                "error": None,
                "trigger_source": trigger_source,
            }
        return owner_token

    def singleflight_finish(
        self,
        cache_key: str,
        *,
        owner_token: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        event: Optional[threading.Event] = None
        with self._lock_guard:
            entry = self._registry.get(cache_key)
            if not isinstance(entry, dict):
                return
            if entry.get("owner_token") != owner_token:
                return
            if entry.get("status") != "running":
                return
            entry["status"] = status
            entry["finished_at"] = self._now_iso()
            entry["error"] = error
            event = entry.get("event")
            self._futures.pop(cache_key, None)
            self._cancel_events.pop(cache_key, None)
        if isinstance(event, threading.Event):
            event.set()

    def _singleflight_wait_for_existing(self, cache_key: str, timeout_secs: float) -> Dict[str, Any]:
        event: Optional[threading.Event] = None
        with self._lock_guard:
            entry = self._registry.get(cache_key)
            if not isinstance(entry, dict) or entry.get("status") != "running":
                return {
                    "waited": False,
                    "running_after_wait": False,
                    "status": entry.get("status") if isinstance(entry, dict) else None,
                }
            event = entry.get("event")
        if not isinstance(event, threading.Event):
            return {"waited": False, "running_after_wait": False, "status": None}
        event.wait(max(timeout_secs, 0.0))
        with self._lock_guard:
            latest = self._registry.get(cache_key)
            running_after_wait = bool(isinstance(latest, dict) and latest.get("status") == "running")
            status = latest.get("status") if isinstance(latest, dict) else None
        return {"waited": True, "running_after_wait": running_after_wait, "status": status}

    def wait_for_inflight_content(
        self,
        *,
        user_id: str,
        goal_id: int,
        session_index: int,
        timeout_secs: float,
    ) -> Dict[str, Any]:
        cache_key = self.content_cache_key(user_id, goal_id, session_index)
        return self._singleflight_wait_for_existing(cache_key, timeout_secs)

    def wait_for_inflight_terminal(
        self,
        *,
        user_id: str,
        goal_id: int,
        session_index: int,
    ) -> Dict[str, Any]:
        cache_key = self.content_cache_key(user_id, goal_id, session_index)
        started = time.perf_counter()
        while True:
            event: Optional[threading.Event] = None
            status: Optional[str] = None
            with self._lock_guard:
                entry = self._registry.get(cache_key)
                if not isinstance(entry, dict):
                    status = None
                else:
                    status = str(entry.get("status"))
                    if status == "running":
                        event = entry.get("event")
            if status != "running":
                return {
                    "status": status,
                    "duration_ms": (time.perf_counter() - started) * 1000.0,
                }
            if not isinstance(event, threading.Event):
                return {
                    "status": "running",
                    "duration_ms": (time.perf_counter() - started) * 1000.0,
                }
            event.wait(1.0)

    def singleflight_status(self, cache_key: str) -> Optional[str]:
        with self._lock_guard:
            entry = self._registry.get(cache_key)
            if isinstance(entry, dict):
                return str(entry.get("status"))
        return None

    @classmethod
    def _normalize_session_for_guard(cls, session: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(session)
        for key in cls._SESSION_GUARD_EXCLUDED_FIELDS:
            normalized.pop(key, None)
        return normalized

    @classmethod
    def session_guard_hash(cls, session: Dict[str, Any]) -> str:
        normalized = cls._normalize_session_for_guard(session)
        encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def session_guard_hash_for_target(self, user_id: str, goal_id: int, session_index: int) -> Optional[str]:
        goal = self._store.get_goal(user_id, goal_id) or {}
        learning_path = goal.get("learning_path", [])
        if (
            not isinstance(learning_path, list)
            or session_index < 0
            or session_index >= len(learning_path)
            or not isinstance(learning_path[session_index], dict)
        ):
            return None
        return self.session_guard_hash(learning_path[session_index])

    def is_stale_for_target_session(
        self,
        *,
        user_id: str,
        goal_id: int,
        session_index: int,
        session_guard_hash_at_start: Optional[str],
    ) -> tuple[bool, Optional[str], str]:
        goal_now = self._store.get_goal(user_id, goal_id) or {}
        path_hash_current = self._path_hash_fn(goal_now)
        learning_path = goal_now.get("learning_path", [])
        if not isinstance(learning_path, list) or session_index < 0 or session_index >= len(learning_path):
            return True, "session_removed", path_hash_current
        session_now = learning_path[session_index]
        if not isinstance(session_now, dict):
            return True, "session_invalid", path_hash_current
        if bool(session_now.get("if_learned", False)):
            return True, "session_learned", path_hash_current
        if session_guard_hash_at_start is None:
            return True, "session_missing_at_start", path_hash_current
        current_guard_hash = self.session_guard_hash(session_now)
        if current_guard_hash != session_guard_hash_at_start:
            return True, "session_changed", path_hash_current
        return False, None, path_hash_current

    def _run_prefetch_worker(
        self,
        *,
        user_id: str,
        goal_id: int,
        session_index: int,
        owner_token: str,
        path_hash_at_start: str,
        trigger_source: str,
        session_guard_hash_at_start: Optional[str],
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        cache_key = self.content_cache_key(user_id, goal_id, session_index)
        started = time.perf_counter()
        stale_reason: Optional[str] = None
        path_hash_current = path_hash_at_start
        self.log_content_event(
            "worker_start",
            user_id=user_id,
            goal_id=goal_id,
            session_index=session_index,
            trigger_source=trigger_source,
            status="running",
            path_hash=path_hash_at_start,
            duration_ms=0.0,
        )
        status = "failed"
        error: Optional[str] = None
        try:
            goal = self._store.get_goal(user_id, goal_id) or {}
            learning_path = goal.get("learning_path", [])
            if (
                not isinstance(learning_path, list)
                or session_index < 0
                or session_index >= len(learning_path)
                or not isinstance(learning_path[session_index], dict)
                or bool(learning_path[session_index].get("if_learned", False))
            ):
                status = "discarded"
                stale_reason = "session_unavailable_at_start"
                return
            if self._store.get_learning_content(user_id, goal_id, session_index):
                status = "succeeded"
                return
            if cancel_event is not None and cancel_event.is_set():
                status = "cancelled"
                stale_reason = "cancel_requested_before_llm"
                return
            learner_profile = self._store.get_profile(user_id, goal_id) or {}
            llm = self._get_llm()
            learning_content = self._build_learning_content_payload(
                llm,
                learner_profile=learner_profile,
                learning_path=learning_path,
                learning_session=learning_path[session_index],
                use_search=True,
                allow_parallel=True,
                with_quiz=True,
                goal_context=goal.get("goal_context"),
                method_name="ami",
                cancel_event=cancel_event,
            )
            stale, stale_reason_now, path_hash_current = self.is_stale_for_target_session(
                user_id=user_id,
                goal_id=goal_id,
                session_index=session_index,
                session_guard_hash_at_start=session_guard_hash_at_start,
            )
            if stale:
                status = "discarded"
                stale_reason = stale_reason_now
                return
            self._store.upsert_learning_content(
                user_id,
                goal_id,
                session_index,
                learning_content,
            )
            status = "succeeded"
        except ContentGenerationCancelled:
            status = "cancelled"
            stale_reason = "cancelled_mid_pipeline"
        except Exception as exc:
            status = "failed"
            error = str(exc)
            self._logger.warning(
                "Prefetch failed for %s g=%s s=%s (%s): %s",
                user_id,
                goal_id,
                session_index,
                trigger_source,
                exc,
            )
        finally:
            self.log_content_event(
                "worker_finish",
                user_id=user_id,
                goal_id=goal_id,
                session_index=session_index,
                trigger_source=trigger_source,
                status=status,
                path_hash=path_hash_at_start,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                error=error,
                stale_reason=stale_reason,
                path_hash_current=path_hash_current,
            )
            self.singleflight_finish(cache_key, owner_token=owner_token, status=status, error=error)

    def enqueue_for_session(
        self,
        *,
        user_id: str,
        goal_id: int,
        session_index: int,
        trigger_source: str,
        apply_cooldown: bool = False,
    ) -> str:
        started = time.perf_counter()
        path_hash = self.current_path_hash(user_id, goal_id)
        if not self.prefetch_enabled():
            self.log_content_event(
                "enqueue_decision",
                user_id=user_id,
                goal_id=goal_id,
                session_index=session_index,
                trigger_source=trigger_source,
                status="disabled",
                path_hash=path_hash,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
            return "disabled"
        if session_index < 0:
            self.log_content_event(
                "enqueue_decision",
                user_id=user_id,
                goal_id=goal_id,
                session_index=session_index,
                trigger_source=trigger_source,
                status="no_candidate",
                path_hash=path_hash,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
            return "no_candidate"

        goal = self._store.get_goal(user_id, goal_id) or {}
        learning_path = goal.get("learning_path", [])
        path_hash = self._path_hash_fn(goal)
        if (
            not isinstance(learning_path, list)
            or session_index >= len(learning_path)
            or not isinstance(learning_path[session_index], dict)
            or bool(learning_path[session_index].get("if_learned", False))
        ):
            self.log_content_event(
                "enqueue_decision",
                user_id=user_id,
                goal_id=goal_id,
                session_index=session_index,
                trigger_source=trigger_source,
                status="no_candidate",
                path_hash=path_hash,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
            return "no_candidate"
        if self._store.get_learning_content(user_id, goal_id, session_index):
            self.log_content_event(
                "enqueue_decision",
                user_id=user_id,
                goal_id=goal_id,
                session_index=session_index,
                trigger_source=trigger_source,
                status="cached",
                path_hash=path_hash,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
            return "cached"

        cache_key = self.content_cache_key(user_id, goal_id, session_index)
        session_guard_hash_at_start = self.session_guard_hash(learning_path[session_index])
        now_ts: Optional[float] = None
        if apply_cooldown:
            now_ts = time.time()
            with self._lock_guard:
                last_ts = self._last_trigger_at.get(cache_key)
                if last_ts is not None and now_ts - last_ts < self.prefetch_cooldown_secs():
                    self.log_content_event(
                        "enqueue_decision",
                        user_id=user_id,
                        goal_id=goal_id,
                        session_index=session_index,
                        trigger_source=trigger_source,
                        status="cooldown",
                        path_hash=path_hash,
                        duration_ms=(time.perf_counter() - started) * 1000.0,
                    )
                    return "cooldown"

        cancel_event = threading.Event()
        owner_token = self.singleflight_try_start(
            cache_key,
            path_hash_at_start=path_hash,
            trigger_source=trigger_source,
            session_guard_hash_at_start=session_guard_hash_at_start,
        )
        if owner_token is None:
            self.log_content_event(
                "enqueue_decision",
                user_id=user_id,
                goal_id=goal_id,
                session_index=session_index,
                trigger_source=trigger_source,
                status="inflight",
                path_hash=path_hash,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
            return "inflight"
        if apply_cooldown and now_ts is not None:
            with self._lock_guard:
                self._last_trigger_at[cache_key] = now_ts
        with self._lock_guard:
            self._cancel_events[cache_key] = cancel_event
        try:
            future = self._executor.submit(
                self._run_prefetch_worker,
                user_id=user_id,
                goal_id=goal_id,
                session_index=session_index,
                owner_token=owner_token,
                path_hash_at_start=path_hash,
                trigger_source=trigger_source,
                session_guard_hash_at_start=session_guard_hash_at_start,
                cancel_event=cancel_event,
            )
            with self._lock_guard:
                self._futures[cache_key] = future
        except Exception as exc:
            self.singleflight_finish(
                cache_key,
                owner_token=owner_token,
                status="failed",
                error=str(exc),
            )
            self.log_content_event(
                "enqueue_decision",
                user_id=user_id,
                goal_id=goal_id,
                session_index=session_index,
                trigger_source=trigger_source,
                status="failed",
                path_hash=path_hash,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                error=str(exc),
            )
            return "failed"
        self.log_content_event(
            "enqueue_decision",
            user_id=user_id,
            goal_id=goal_id,
            session_index=session_index,
            trigger_source=trigger_source,
            status="queued",
            path_hash=path_hash,
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
        return "queued"

    def enqueue_for_goal(
        self,
        *,
        user_id: str,
        goal_id: int,
        trigger_source: str,
        start_after: int = -1,
        apply_cooldown: bool = False,
    ) -> str:
        goal = self._store.get_goal(user_id, goal_id) or {}
        target_idx = self.first_unlearned_session_index(
            goal.get("learning_path", []),
            start_after=start_after,
        )
        if target_idx is None:
            self.log_content_event(
                "enqueue_decision",
                user_id=user_id,
                goal_id=goal_id,
                session_index=-1,
                trigger_source=trigger_source,
                status="no_candidate",
                path_hash=self._path_hash_fn(goal),
                duration_ms=0.0,
            )
            return "no_candidate"
        return self.enqueue_for_session(
            user_id=user_id,
            goal_id=goal_id,
            session_index=target_idx,
            trigger_source=trigger_source,
            apply_cooldown=apply_cooldown,
        )

    @staticmethod
    def _session_signature(session: Any) -> str:
        if not isinstance(session, dict):
            return "__invalid__"
        return json.dumps(session, ensure_ascii=False, sort_keys=True, default=str)

    def changed_unlearned_indices(self, before_path: Any, after_path: Any) -> List[int]:
        before: Dict[int, str] = {}
        after: Dict[int, str] = {}
        if isinstance(before_path, list):
            for idx, session in enumerate(before_path):
                if isinstance(session, dict) and not bool(session.get("if_learned", False)):
                    before[idx] = self._session_signature(session)
        if isinstance(after_path, list):
            for idx, session in enumerate(after_path):
                if isinstance(session, dict) and not bool(session.get("if_learned", False)):
                    after[idx] = self._session_signature(session)
        changed = sorted(
            idx for idx in set(before.keys()) | set(after.keys())
            if before.get(idx) != after.get(idx)
        )
        return changed

    def invalidate_learning_content_indices(self, user_id: str, goal_id: int, indices: List[int]) -> None:
        for idx in indices:
            if isinstance(idx, int) and idx >= 0:
                self._store.delete_learning_content(user_id, goal_id, idx)

    def cancel_inflight_for_goal(self, user_id: str, goal_id: int) -> int:
        """Best-effort cancel all running/queued prefetch workers for the given goal.

        For tasks not yet started: Future.cancel() prevents execution and the registry
        entry is finalized immediately. For tasks already running: the cancel_event is
        set so the pipeline stops at the next stage checkpoint. Tasks mid-LLM-call fall
        back to the staleness check after the call completes.

        Returns the number of running entries that were targeted for cancellation.
        """
        prefix = f"{user_id}:{goal_id}:"
        cancelled_count = 0
        events_to_signal: List[threading.Event] = []

        with self._lock_guard:
            for key, entry in list(self._registry.items()):
                if not key.startswith(prefix):
                    continue
                if not isinstance(entry, dict) or entry.get("status") != "running":
                    continue

                # Signal the pipeline cancel event so checkpoints can exit early
                cancel_event = self._cancel_events.get(key)
                if isinstance(cancel_event, threading.Event):
                    cancel_event.set()

                # Try to stop the task before it starts executing
                future = self._futures.get(key)
                future_stopped = future is not None and future.cancel()

                entry["cancel_requested"] = True
                if future_stopped:
                    # Task never ran — finalize the registry entry now
                    entry["status"] = "cancelled"
                    entry["finished_at"] = self._now_iso()
                    entry["error"] = "cancel_requested_before_start"
                    singleflight_event = entry.get("event")
                    if isinstance(singleflight_event, threading.Event):
                        events_to_signal.append(singleflight_event)
                    self._futures.pop(key, None)
                    self._cancel_events.pop(key, None)

                cancelled_count += 1

        for event in events_to_signal:
            event.set()

        return cancelled_count

    def reset_for_test(self) -> None:
        with self._lock_guard:
            self._registry.clear()
            self._last_trigger_at.clear()
            self._futures.clear()
            self._cancel_events.clear()
