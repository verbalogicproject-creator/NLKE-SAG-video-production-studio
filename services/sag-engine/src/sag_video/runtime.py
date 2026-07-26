from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .models import utc_now


RUNTIME_RETENTION_DAYS = 7
RUNTIME_MAX_EVENTS = 50_000
RUNTIME_PAYLOAD_LIMIT = 16_384
_SENSITIVE_KEY = re.compile(
    r"(^|_)(authorization|cookie|credential|password|prompt|secret|token|media_bytes|raw_output)($|_)",
    re.IGNORECASE,
)


class RuntimeEventDefinition(BaseModel):
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,119}$")
    version: int = Field(default=1, ge=1)
    json_schema: dict[str, Any]
    release_status: Literal["released", "experimental"] = "released"
    retention_class: Literal["runtime_7d", "audit"] = "runtime_7d"
    source_hash: str = ""

    def with_hash(self) -> "RuntimeEventDefinition":
        body = self.model_dump(mode="json", exclude={"source_hash"})
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"source_hash": digest})


class RuntimeEvent(BaseModel):
    cursor: int = Field(ge=1)
    event_id: str
    workspace_id: str
    project_id: str
    sequence_id: str
    revision: int = Field(ge=1)
    actor: str
    session_id: str | None = None
    kind: str
    trace_id: str | None = None
    payload: dict[str, Any]
    created_at: str
    expires_at: str


def _schema(required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": True,
        "required": required or [],
        "properties": {},
    }


EVENT_DEFINITIONS = tuple(
    definition.with_hash()
    for definition in (
        RuntimeEventDefinition(kind="studio.depth_changed", json_schema=_schema(["active_depth"])),
        RuntimeEventDefinition(kind="studio.focus_changed", json_schema=_schema(["entity_ids"])),
        RuntimeEventDefinition(kind="command.committed", json_schema=_schema(["command"]), retention_class="audit"),
        RuntimeEventDefinition(kind="command.denied", json_schema=_schema(["command", "reason"]), retention_class="audit"),
        RuntimeEventDefinition(kind="job.state_changed", json_schema=_schema(["job_id", "state"])),
        RuntimeEventDefinition(kind="artifact.observed", json_schema=_schema(["artifact_id"]), retention_class="audit"),
        RuntimeEventDefinition(kind="receipt.transitioned", json_schema=_schema(["receipt_id", "status"]), retention_class="audit"),
        RuntimeEventDefinition(kind="release.transitioned", json_schema=_schema()),
        RuntimeEventDefinition(kind="publication.transitioned", json_schema=_schema()),
        RuntimeEventDefinition(kind="actor.connected", json_schema=_schema(["actor"])),
        RuntimeEventDefinition(kind="actor.focus_changed", json_schema=_schema(["entity_ids"])),
        RuntimeEventDefinition(kind="actor.disconnected", json_schema=_schema(["actor"])),
        RuntimeEventDefinition(kind="spatial.directive.dispatched", json_schema=_schema(["receipt_id", "action"]), retention_class="audit"),
        RuntimeEventDefinition(kind="spatial.directive.consumed", json_schema=_schema(["receipt_id"]), retention_class="audit"),
        RuntimeEventDefinition(kind="spatial.directive.failed", json_schema=_schema(["receipt_id"]), retention_class="audit"),
        RuntimeEventDefinition(kind="spatial.directive.timeout", json_schema=_schema(["receipt_id"]), retention_class="audit"),
        RuntimeEventDefinition(
            kind="spatial.frame.declared", version=1,
            json_schema=_schema(["frame"]), release_status="experimental",
        ),
        RuntimeEventDefinition(
            kind="spatial.bindings.reconciled", version=1,
            json_schema=_schema(["frame_id", "bindings"]), release_status="experimental",
        ),
        RuntimeEventDefinition(
            kind="spatial.action.routed", version=1,
            json_schema=_schema(["action", "route"]), release_status="experimental",
        ),
        RuntimeEventDefinition(
            kind="spatial.effect.observed", version=1,
            json_schema=_schema(["observation"]), release_status="experimental",
        ),
    )
)


def sanitize_payload(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:1024]
    if isinstance(value, bytes):
        return "[binary omitted]"
    if isinstance(value, list):
        return [sanitize_payload(entry, depth=depth + 1) for entry in value[:100]]
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for raw_key, entry in list(value.items())[:100]:
            key = str(raw_key)[:120]
            if _SENSITIVE_KEY.search(key):
                clean[key] = "[redacted]"
            else:
                clean[key] = sanitize_payload(entry, depth=depth + 1)
        return clean
    return str(value)[:1024]


def bounded_payload(payload: dict[str, Any]) -> dict[str, Any]:
    clean = sanitize_payload(payload)
    encoded = json.dumps(clean, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > RUNTIME_PAYLOAD_LIMIT:
        return {
            "truncated": True,
            "sha256": hashlib.sha256(encoded.encode()).hexdigest(),
            "original_bytes": len(encoded.encode()),
        }
    return clean


class RuntimeBroker:
    """Persisted cursor is truth; this condition is only a local wake hint."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._generation = 0

    def notify(self, payload: dict[str, Any] | None = None) -> None:
        with self._condition:
            self._generation += 1
            self._condition.notify_all()

    async def wait(self, generation: int, timeout: float = 10.0) -> int:
        def blocking_wait() -> int:
            with self._condition:
                if self._generation == generation:
                    self._condition.wait(timeout)
                return self._generation

        return await asyncio.to_thread(blocking_wait)

    @property
    def generation(self) -> int:
        with self._condition:
            return self._generation

    def close(self) -> None:
        return None


class PostgreSQLRuntimeBroker(RuntimeBroker):
    """Cross-instance wake hints. Persisted rows remain the delivery authority."""

    CHANNEL = "sag_runtime_wakeup"

    def __init__(self, database_url: str) -> None:
        super().__init__()
        self.database_url = database_url
        self._closed = threading.Event()
        self._publisher_lock = threading.Lock()
        self._publisher: Any | None = None
        self._listener = threading.Thread(target=self._listen, name="sag-runtime-listener", daemon=True)
        self._listener.start()

    @staticmethod
    def _connect(database_url: str) -> Any:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover - deployment dependency guard
            raise RuntimeError("PostgreSQL runtime broker requires psycopg") from error
        return psycopg.connect(database_url, autocommit=True)

    def _wake_local(self) -> None:
        super().notify()

    def _listen(self) -> None:  # pragma: no cover - exercised by PostgreSQL acceptance
        delay = 0.25
        while not self._closed.is_set():
            try:
                connection = self._connect(self.database_url)
                connection.execute(f"LISTEN {self.CHANNEL}")
                delay = 0.25
                while not self._closed.is_set():
                    for _notification in connection.notifies(timeout=1.0, stop_after=1):
                        self._wake_local()
                connection.close()
            except Exception:
                if self._closed.wait(delay):
                    break
                delay = min(delay * 2, 5.0)

    def notify(self, payload: dict[str, Any] | None = None) -> None:
        self._wake_local()
        encoded = json.dumps(sanitize_payload(payload or {}), sort_keys=True, separators=(",", ":"))[:2048]
        try:
            with self._publisher_lock:
                if self._publisher is None or getattr(self._publisher, "closed", False):
                    self._publisher = self._connect(self.database_url)
                self._publisher.execute("SELECT pg_notify(%s, %s)", (self.CHANNEL, encoded))
        except Exception:
            with self._publisher_lock:
                publisher, self._publisher = self._publisher, None
                if publisher is not None:
                    try:
                        publisher.close()
                    except Exception:
                        pass

    def close(self) -> None:
        self._closed.set()
        with self._publisher_lock:
            publisher, self._publisher = self._publisher, None
            if publisher is not None:
                try:
                    publisher.close()
                except Exception:
                    pass
        self._listener.join(timeout=2)


def create_runtime_broker(*, backend: str, database_url: str = "") -> RuntimeBroker:
    if backend == "postgres":
        return PostgreSQLRuntimeBroker(database_url)
    return RuntimeBroker()


class RuntimeEventService:
    def __init__(self, store: Any, broker: RuntimeBroker | None = None):
        self.store = store
        self.broker = broker or RuntimeBroker()
        self.store.reconcile_event_definitions(EVENT_DEFINITIONS)

    def emit(
        self,
        *,
        workspace_id: str,
        project_id: str,
        sequence_id: str,
        revision: int,
        actor: str,
        kind: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
        session_id: str | None = None,
    ) -> RuntimeEvent:
        event = self.store.append_runtime_event(
            event_id=f"event_{uuid4().hex}",
            workspace_id=workspace_id,
            project_id=project_id,
            sequence_id=sequence_id,
            revision=revision,
            actor=actor,
            session_id=session_id,
            kind=kind,
            trace_id=trace_id,
            payload=bounded_payload(payload),
            created_at=utc_now(),
            expires_at=(datetime.now(timezone.utc) + timedelta(days=RUNTIME_RETENTION_DAYS)).isoformat(),
        )
        self.store.prune_runtime_events(project_id, max_events=RUNTIME_MAX_EVENTS)
        self.broker.notify({
            "workspace_id": workspace_id, "project_id": project_id,
            "sequence_id": sequence_id, "cursor": event["cursor"],
        })
        return RuntimeEvent.model_validate(event)

    def definitions(self) -> list[dict[str, Any]]:
        return [definition.model_dump(mode="json") for definition in EVENT_DEFINITIONS]

    def history(self, project_id: str, *, after_cursor: int = 0, limit: int = 200) -> list[RuntimeEvent]:
        return [RuntimeEvent.model_validate(row) for row in self.store.list_runtime_events(
            project_id, after_cursor=after_cursor, limit=max(1, min(limit, 1000))
        )]

    def prune(self, project_id: str) -> int:
        return self.store.prune_runtime_events(project_id, max_events=RUNTIME_MAX_EVENTS)
