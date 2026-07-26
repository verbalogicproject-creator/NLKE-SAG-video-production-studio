from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field


JOURNAL_PROTOCOL_VERSION = "sag-journal/0.1-draft"
CHAIN_VERSION = 1
JOURNAL_SCHEMA_VERSION = 1
GENESIS = "0" * 64
MAX_CONTENT_BYTES = 64 * 1024

DEFAULT_JOURNAL_KINDS = (
    "decision", "gotcha", "insight", "invariant", "task", "milestone", "general",
    "sag.retrieval", "sag.context_load", "sag.receipt", "sag.observation", "sag.claim", "sag.trust",
)

_SECRET_MARKERS = (
    ("pem-private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
)


class InadmissibleJournalPayload(ValueError):
    pass


class JournalEntryRequest(BaseModel):
    id: str = Field(min_length=1, max_length=256)
    kind: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=MAX_CONTENT_BYTES)
    session_id: str | None = Field(default=None, max_length=256)
    batch: str | None = Field(default=None, max_length=256)
    tags: list[str] = Field(default_factory=list, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    method: str = Field(default="manual", min_length=1, max_length=120)
    schema_version: int = Field(default=JOURNAL_SCHEMA_VERSION, ge=1)
    created_at: str
    hash_alg: Literal["sha256", "hmac-sha256"] = "sha256"


class JournalEntry(BaseModel):
    namespace: str
    seq: int | None
    prev_hash: str | None
    row_hash: str | None
    hash_alg: str | None
    id: str
    kind: str
    content: str
    session_id: str | None
    batch: str | None
    tags: list[str]
    metadata: dict[str, Any]
    method: str
    schema_version: int
    created_at: str


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def journal_preimage(*, namespace: str, seq: int, prev_hash: str, entry: JournalEntryRequest) -> bytes:
    return canonical_bytes({
        "v": CHAIN_VERSION, "ns": namespace or "", "seq": seq, "prev": prev_hash,
        "id": entry.id, "kind": entry.kind, "content": entry.content,
        "session_id": entry.session_id, "batch": entry.batch, "tags": entry.tags,
        "metadata": entry.metadata, "method": entry.method,
        "schema_version": entry.schema_version, "created_at": entry.created_at,
    })


def compute_journal_hash(algorithm: str | None, key: str | bytes | None, preimage: bytes) -> str:
    if algorithm in {None, "sha256"}:
        return hashlib.sha256(preimage).hexdigest()
    if algorithm == "hmac-sha256":
        if key is None:
            raise ValueError("hash_alg 'hmac-sha256' requires an out-of-band key")
        key_bytes = key.encode("utf-8") if isinstance(key, str) else bytes(key)
        return hmac.new(key_bytes, preimage, hashlib.sha256).hexdigest()
    raise ValueError(f"unknown journal hash algorithm: {algorithm}")


def _validate_metadata(value: Any, *, path: str = "metadata") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise InadmissibleJournalPayload(f"{path}: floats are not permitted; use a declared decimal string")
    if isinstance(value, (bytes, bytearray)):
        raise InadmissibleJournalPayload(f"{path}: raw bytes are not permitted")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise InadmissibleJournalPayload(f"{path}: object keys must be strings")
            _validate_metadata(child, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_metadata(child, path=f"{path}[{index}]")
        return
    raise InadmissibleJournalPayload(f"{path}: unsupported type {type(value).__name__}")


def validate_journal_payload(entry: JournalEntryRequest) -> None:
    if not entry.content.strip():
        raise InadmissibleJournalPayload("entry content must be non-empty")
    size = len(entry.content.encode("utf-8"))
    if size > MAX_CONTENT_BYTES:
        raise InadmissibleJournalPayload(f"content is {size} bytes, over the {MAX_CONTENT_BYTES}-byte cap")
    for name, pattern in _SECRET_MARKERS:
        if pattern.search(entry.content):
            raise InadmissibleJournalPayload(f"content matches a {name} marker")
    _validate_metadata(entry.metadata)


def _kind_definition(kind: str) -> dict[str, Any]:
    body = {"kind": kind, "version": 1, "protocol": JOURNAL_PROTOCOL_VERSION, "release_status": "draft"}
    return {**body, "source_hash": hashlib.sha256(canonical_bytes(body)).hexdigest()}


JOURNAL_KIND_DEFINITIONS = tuple(_kind_definition(kind) for kind in DEFAULT_JOURNAL_KINDS)


def journal_schemas() -> dict[str, Any]:
    return {
        "JournalEntryRequest": JournalEntryRequest.model_json_schema(),
        "JournalEntry": JournalEntry.model_json_schema(),
    }


class SagJournalService:
    """Independent sag-journal/0.1-draft adapter over the configured SAG repository."""

    def __init__(self, store: Any, *, hash_key: str | bytes | None = None):
        self.store = store
        self.hash_key = hash_key
        self.store.reconcile_journal_kinds(JOURNAL_KIND_DEFINITIONS)

    def append(self, namespace: str, request: JournalEntryRequest) -> tuple[JournalEntry, bool]:
        validate_journal_payload(request)
        with self.store.transaction():
            existing = self.store.get_journal_entry(namespace, request.id)
            if existing is not None:
                return JournalEntry.model_validate(existing), False
            if not self.store.journal_kind_registered(request.kind):
                raise ValueError(f"journal kind must be registered before emit: {request.kind}")
            head_seq, head_hash, head_alg = self.store.get_journal_head_for_update(namespace, request.hash_alg)
            existing = self.store.get_journal_entry(namespace, request.id)
            if existing is not None:
                return JournalEntry.model_validate(existing), False
            if head_seq and head_alg != request.hash_alg:
                raise ValueError("journal hash algorithm cannot change within a namespace")
            seq = head_seq + 1
            prev_hash = head_hash or GENESIS
            row_hash = compute_journal_hash(
                request.hash_alg, self.hash_key,
                journal_preimage(namespace=namespace, seq=seq, prev_hash=prev_hash, entry=request),
            )
            stored = self.store.insert_journal_entry({
                "namespace": namespace, "seq": seq, "prev_hash": prev_hash,
                "row_hash": row_hash, **request.model_dump(mode="json"),
            })
            self.store.advance_journal_head(namespace, seq, row_hash, request.hash_alg)
        return JournalEntry.model_validate(stored), True

    def entries(self, namespace: str, *, limit: int = 200) -> list[JournalEntry]:
        return [JournalEntry.model_validate(row) for row in self.store.list_journal_entries(namespace, limit=limit)]

    def verify(self, namespace: str) -> dict[str, Any]:
        rows = self.store.list_journal_entries(namespace, limit=1_000_000, include_unchained=False)
        unchained = self.store.count_unchained_journal_entries(namespace)
        expected_seq = 1
        expected_prev = GENESIS
        checked = 0
        last_hash: str | None = None
        last_alg: str | None = rows[-1]["hash_alg"] if rows else "sha256"
        for row in rows:
            last_alg = row["hash_alg"]
            if row["seq"] != expected_seq:
                return self._break("sequence-gap", expected_seq, row["id"], expected_seq, row["seq"], checked, unchained, last_hash, last_alg)
            if row["prev_hash"] != expected_prev:
                return self._break("predecessor-mismatch", expected_seq, row["id"], expected_prev, row["prev_hash"], checked, unchained, last_hash, last_alg)
            request = JournalEntryRequest.model_validate({
                key: row[key] for key in (
                    "id", "kind", "content", "session_id", "batch", "tags", "metadata",
                    "method", "schema_version", "created_at", "hash_alg",
                )
            })
            recomputed = compute_journal_hash(
                row["hash_alg"], self.hash_key,
                journal_preimage(namespace=namespace, seq=row["seq"], prev_hash=row["prev_hash"], entry=request),
            )
            if recomputed != row["row_hash"]:
                return self._break("row-hash-mismatch", expected_seq, row["id"], recomputed, row["row_hash"], checked, unchained, last_hash, last_alg)
            expected_prev = row["row_hash"]
            last_hash = row["row_hash"]
            expected_seq += 1
            checked += 1
        return {
            "ok": True, "break": None, "at_seq": None, "at_id": None,
            "expected": None, "found": None, "checked": checked, "unchained": unchained,
            "head_hash": last_hash, "alg": last_alg,
        }

    @staticmethod
    def _break(
        kind: str, at_seq: int, at_id: str, expected: Any, found: Any,
        checked: int, unchained: int, last_hash: str | None, last_alg: str | None,
    ) -> dict[str, Any]:
        return {
            "ok": False, "break": kind, "at_seq": at_seq, "at_id": at_id,
            "expected": expected, "found": found, "checked": checked, "unchained": unchained,
            "head_hash": last_hash, "alg": last_alg,
        }
