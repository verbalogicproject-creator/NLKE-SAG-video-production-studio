"""Workspace-scoped, profile-governed browser computer-use contracts."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .blob_storage import BlobStorage, StorageLocator
from .commands import CommandService
from .contracts import COMMAND_REGISTRY
from .models import CommandRequest, utc_now


COMPUTER_USE_SCHEMA_VERSION = "sag-computer-use/1.0"
PROFILE_SCHEMA_VERSION = "sag-computer-use-profile/1.0"
COMPUTER_USE_SCOPES = (
    "computer_use:observe", "computer_use:act", "computer_use:capture", "computer_use:attach",
)
BUILTIN_TRUSTED_KEYS = {
    # Public verification material only. Deployment-specific profiles should
    # use SAG_COMPUTER_USE_TRUSTED_KEYS; signing keys never belong in SAG.
    "sag-v1-2026-07": "O7S1luFHte5FVMbTpLY0PZtzhfyQ1Wlj5StGDxxaM_w",
}


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _canonical(value: Any) -> bytes:
    # Profiles intentionally admit only the JSON subset whose Python and browser
    # canonical forms are identical (no NaN, Infinity, or floating locators).
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def normalize_computer_use_origin(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("origin must not contain credentials, path, query, or fragment")
    if parsed.scheme in {"http", "https"} and host:
        return f"{parsed.scheme}://{parsed.netloc.lower()}"
    raise ValueError("origin must use HTTP or HTTPS")


class ComputerUseLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["sag_entity", "aria", "label", "test_id"]
    value: str = Field(min_length=1, max_length=240)


class ComputerUseProfileEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str = Field(min_length=1, max_length=200)
    role: str = Field(default="region", min_length=1, max_length=80)
    locator: ComputerUseLocator


class ComputerUseProfileAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str = Field(min_length=3, max_length=160)
    entity_ids: list[str] = Field(min_length=1, max_length=32)
    route: Literal["observer_only", "extension_handler", "canonical_command"]
    safety_class: Literal[
        "read", "safe_reversible", "costed_reversible", "destructive_confirmation",
        "human_approval_only", "credential_admin_only", "ineligible",
    ] = "safe_reversible"
    required_scope: str = Field(default="computer_use:act", min_length=3, max_length=120)
    arguments_schema: dict[str, Any] = Field(default_factory=dict)
    effect_predicates: list[Literal[
        "state_hash_changed", "canonical_revision_increment", "target_visible", "target_selected",
    ]] = Field(default_factory=list, max_length=8)
    compensation_action_id: str | None = Field(default=None, max_length=160)
    checkpoint_policy: Literal["none", "explicit", "before_after_required"] = "explicit"

    @model_validator(mode="after")
    def reversible_actions_have_compensation(self) -> "ComputerUseProfileAction":
        if self.safety_class == "safe_reversible" and not self.compensation_action_id:
            raise ValueError("safe reversible actions require a compensation_action_id")
        return self


class ComputerUseProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["sag-computer-use-profile/1.0"] = PROFILE_SCHEMA_VERSION
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,119}$")
    version: int = Field(ge=1)
    issuer: str = Field(min_length=3, max_length=200)
    key_id: str = Field(min_length=3, max_length=160)
    allowed_origins: list[str] = Field(min_length=1, max_length=32)
    adapter_id: str = Field(min_length=3, max_length=160)
    entities: list[ComputerUseProfileEntity] = Field(default_factory=list, max_length=128)
    actions: list[ComputerUseProfileAction] = Field(default_factory=list, max_length=128)
    signature: str = Field(min_length=40, max_length=200)

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        return [normalize_computer_use_origin(value) for value in values]

    @model_validator(mode="after")
    def references_known_entities_and_actions(self) -> "ComputerUseProfile":
        entities = [entry.entity_id for entry in self.entities]
        if len(entities) != len(set(entities)):
            raise ValueError("profile entity IDs must be unique")
        actions = [entry.action_id for entry in self.actions]
        if len(actions) != len(set(actions)):
            raise ValueError("profile action IDs must be unique")
        known = set(entities)
        if any(entity_id not in known for action in self.actions for entity_id in action.entity_ids):
            raise ValueError("profile action references an unknown entity")
        action_set = set(actions)
        if any(
            action.compensation_action_id not in action_set
            for action in self.actions
            if action.compensation_action_id
        ):
            raise ValueError("profile action references an unknown compensation action")
        return self

    def signed_body(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def profile_sha256(self) -> str:
        return _digest(self.signed_body())


class ComputerUseContextRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["project", "incident", "work_order", "evidence_claim", "uri"]
    id: str = Field(min_length=1, max_length=240)
    revision: int | str | None = None


class ComputerUseActivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: str
    tab_session_id: str = Field(min_length=8, max_length=160)
    profile_id: str | None = Field(default=None, max_length=120)
    profile_version: int | None = Field(default=None, ge=1)
    context_refs: list[ComputerUseContextRef] = Field(default_factory=list, max_length=16)

    @field_validator("origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        return normalize_computer_use_origin(value)


class ComputerUseActivityStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["paused"] = "paused"
    reason: str = Field(default="user_paused", min_length=3, max_length=120)


class ComputerUseBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    binding_id: str = Field(min_length=8, max_length=160)
    entity_id: str = Field(min_length=1, max_length=200)
    role: str = Field(default="region", max_length=80)
    label: str = Field(default="", max_length=240)
    rect: dict[Literal["x", "y", "width", "height"], float]
    source: Literal["dom", "accessibility", "profile"]
    confidence: float = Field(default=1, ge=0, le=1)
    visible: bool = True
    protected: bool = False
    eligible_action_ids: list[str] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def bounded_rect(self) -> "ComputerUseBinding":
        if set(self.rect) != {"x", "y", "width", "height"}:
            raise ValueError("binding rectangle requires normalized x, y, width, and height")
        x, y, width, height = (self.rect[key] for key in ("x", "y", "width", "height"))
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1.000001 or y + height > 1.000001:
            raise ValueError("binding rectangle exceeds normalized viewport")
        return self


class ComputerUseObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: str
    route_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    title_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    viewport: dict[str, int | float]
    application_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    bindings: list[ComputerUseBinding] = Field(default_factory=list, max_length=128)
    context_refs: list[ComputerUseContextRef] = Field(default_factory=list, max_length=16)
    redaction_state: Literal["metadata_only", "redacted", "not_applicable"] = "metadata_only"
    spatial_frame_id: str | None = Field(default=None, max_length=160)
    observed_at: str = Field(default_factory=utc_now)

    @field_validator("origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        return normalize_computer_use_origin(value)


class ComputerUseIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=160)
    before_observation_id: str = Field(min_length=8, max_length=160)
    action_id: str = Field(min_length=3, max_length=160)
    target_binding_id: str = Field(min_length=8, max_length=160)
    arguments: dict[str, Any] = Field(default_factory=dict)
    context_ref: ComputerUseContextRef | None = None
    expected_project_revision: int | None = Field(default=None, ge=1)


class ComputerUseExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=32, max_length=200)


class ComputerUseCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_observation_id: str = Field(min_length=8, max_length=160)
    success: bool = True
    observed_effect: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list, max_length=20)


class ComputerUseAttachmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checkpoint_ids: list[str] = Field(default_factory=list, max_length=32)
    context: ComputerUseContextRef


class ComputerUseService:
    def __init__(self, store: Any, commands: CommandService, storage: BlobStorage):
        self.store = store
        self.commands = commands
        self.storage = storage
        configured = json.loads(os.getenv("SAG_COMPUTER_USE_TRUSTED_KEYS", "{}") or "{}")
        self.trusted_keys: dict[str, str] = {
            **BUILTIN_TRUSTED_KEYS,
            **{str(key): str(value) for key, value in configured.items()},
        }

    def ensure_builtin_studio_profile(self, workspace_id: str) -> dict[str, Any]:
        existing = [
            entry for entry in self.list_profiles(workspace_id)
            if entry["profile"]["profile_id"] == "sag.studio.local"
        ]
        if existing:
            return max(existing, key=lambda entry: int(entry["profile"]["version"]))
        path = Path(__file__).parent / "static" / "computer-use-sag-profile.v1.json"
        return self.install_profile(workspace_id, ComputerUseProfile.model_validate_json(path.read_text()))

    def _put(self, workspace_id: str, kind: str, body: dict[str, Any], *, record_id: str | None = None, expected_revision: int = 0, append_only: bool = True) -> dict[str, Any]:
        identity = record_id or f"{kind}_{uuid4().hex[:16]}"
        return self.store.put_editorial_record(
            record_id=identity, kind=kind, body=body, expected_revision=expected_revision,
            workspace_id=workspace_id, append_only=append_only,
        )

    def _get(self, identity: str, kind: str) -> dict[str, Any]:
        return self.store.get_editorial_record(identity, kind=kind)

    def install_profile(self, workspace_id: str, profile: ComputerUseProfile) -> dict[str, Any]:
        public = self.trusted_keys.get(profile.key_id)
        if public is None:
            if os.getenv("SAG_COMPUTER_USE_DEV_PROFILES", "").lower() not in {"1", "true", "yes"}:
                raise ValueError("computer-use profile issuer is not trusted")
            verified = False
        else:
            try:
                Ed25519PublicKey.from_public_bytes(_b64decode(public)).verify(
                    _b64decode(profile.signature), _canonical(profile.signed_body()),
                )
            except (ValueError, InvalidSignature) as error:
                raise ValueError("computer-use profile signature is invalid") from error
            verified = True
        installed = self.store.list_editorial_records(kind="computer_use_profile", workspace_id=workspace_id)
        previous = [int(entry["profile"]["version"]) for entry in installed if entry["profile"]["profile_id"] == profile.profile_id]
        if previous and profile.version <= max(previous):
            existing = next((entry for entry in installed if entry["profile"]["profile_id"] == profile.profile_id and int(entry["profile"]["version"]) == profile.version and entry["profile_sha256"] == profile.profile_sha256), None)
            if existing:
                return existing
            raise ValueError("computer-use profile rollback or conflicting version")
        return self._put(workspace_id, "computer_use_profile", {
            "schema_version": PROFILE_SCHEMA_VERSION, "workspace_id": workspace_id,
            "profile": profile.model_dump(mode="json"), "profile_sha256": profile.profile_sha256,
            "signature_verified": verified, "installed_at": utc_now(),
        })

    def list_profiles(self, workspace_id: str, *, origin: str | None = None) -> list[dict[str, Any]]:
        records = self.store.list_editorial_records(kind="computer_use_profile", workspace_id=workspace_id)
        normalized = normalize_computer_use_origin(origin) if origin else None
        return [entry for entry in records if normalized is None or normalized in entry["profile"]["allowed_origins"]]

    def _profile(self, workspace_id: str, profile_id: str, version: int | None = None) -> dict[str, Any]:
        matches = [entry for entry in self.list_profiles(workspace_id) if entry["profile"]["profile_id"] == profile_id and (version is None or int(entry["profile"]["version"]) == version)]
        if not matches:
            raise KeyError(profile_id)
        return max(matches, key=lambda entry: int(entry["profile"]["version"]))

    def create_activity(self, workspace_id: str, actor: str, request: ComputerUseActivityRequest) -> dict[str, Any]:
        profile_record = None
        if request.profile_id:
            profile_record = self._profile(workspace_id, request.profile_id, request.profile_version)
            if request.origin not in profile_record["profile"]["allowed_origins"]:
                raise ValueError("computer-use profile does not allow the active origin")
        now = datetime.now(timezone.utc)
        return self._put(workspace_id, "computer_use_activity", {
            "schema_version": COMPUTER_USE_SCHEMA_VERSION, "workspace_id": workspace_id,
            "actor": actor, "origin": request.origin, "tab_session_id": request.tab_session_id,
            "profile_record_id": profile_record["id"] if profile_record else None,
            "profile_id": request.profile_id,
            "profile_version": int(profile_record["profile"]["version"]) if profile_record else None,
            "profile_sha256": profile_record.get("profile_sha256") if profile_record else None,
            "context_refs": [entry.model_dump(mode="json") for entry in request.context_refs],
            "state": "active", "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=8)).isoformat(),
        })

    def get_activity(self, workspace_id: str, activity_id: str) -> dict[str, Any]:
        activity = self._get(activity_id, "computer_use_activity")
        if activity["workspace_id"] != workspace_id:
            raise ValueError("computer-use activity belongs to another workspace")
        return activity

    def list_activities(self, workspace_id: str) -> list[dict[str, Any]]:
        return self.store.list_editorial_records(kind="computer_use_activity", workspace_id=workspace_id)

    def pause_activity(self, workspace_id: str, activity_id: str, reason: str) -> dict[str, Any]:
        activity = self.get_activity(workspace_id, activity_id)
        if activity["state"] == "paused":
            return activity
        return self._put(workspace_id, "computer_use_activity", {
            **{key: value for key, value in activity.items() if key not in {"revision"}},
            "state": "paused", "pause_reason": reason, "paused_at": utc_now(),
        }, record_id=activity_id, expected_revision=int(activity["revision"]), append_only=False)

    def observe(self, workspace_id: str, activity_id: str, request: ComputerUseObservationRequest) -> dict[str, Any]:
        activity = self.get_activity(workspace_id, activity_id)
        if activity["state"] != "active" or datetime.fromisoformat(activity["expires_at"]) < datetime.now(timezone.utc):
            raise ValueError("computer-use activity is not active")
        if request.origin != activity["origin"]:
            self.pause_activity(workspace_id, activity_id, "origin_changed")
            raise ValueError("active tab origin changed")
        prior = self.store.list_editorial_records(kind="computer_use_observation", workspace_id=workspace_id)
        prior = [entry for entry in prior if entry["activity_id"] == activity_id]
        if prior and prior[0]["route_hash"] != request.route_hash:
            self.pause_activity(workspace_id, activity_id, "navigation_detected")
            raise ValueError("active tab navigated; a new user activation is required")
        allowed_actions: dict[str, set[str]] = {}
        if activity.get("profile_id"):
            profile = self._profile(workspace_id, activity["profile_id"], activity.get("profile_version"))["profile"]
            for action in profile["actions"]:
                for entity_id in action["entity_ids"]:
                    allowed_actions.setdefault(entity_id, set()).add(action["action_id"])
        for binding in request.bindings:
            allowed = allowed_actions.get(binding.entity_id, set())
            if any(action not in allowed for action in binding.eligible_action_ids):
                raise ValueError("observation binding claims an undeclared action")
            if not activity.get("profile_id") and binding.eligible_action_ids:
                raise ValueError("unprofiled observations cannot declare actions")
        return self._put(workspace_id, "computer_use_observation", {
            "schema_version": COMPUTER_USE_SCHEMA_VERSION, "workspace_id": workspace_id,
            "activity_id": activity_id, **request.model_dump(mode="json"),
            "observation_hash": _digest(request.model_dump(mode="json")), "recorded_at": utc_now(),
        })

    def actions(self, workspace_id: str, activity_id: str) -> list[dict[str, Any]]:
        activity = self.get_activity(workspace_id, activity_id)
        if activity["state"] != "active" or datetime.fromisoformat(activity["expires_at"]) < datetime.now(timezone.utc):
            return []
        if not activity.get("profile_id"):
            return []
        return self._profile(workspace_id, activity["profile_id"], activity.get("profile_version"))["profile"]["actions"]

    def _checkpoints(self, workspace_id: str, activity_id: str, observation_id: str) -> list[dict[str, Any]]:
        return [
            entry for entry in self.store.list_editorial_records(
                kind="computer_use_checkpoint", workspace_id=workspace_id,
            )
            if entry["activity_id"] == activity_id and entry["observation_id"] == observation_id
        ]

    def _has_checkpoint(self, workspace_id: str, activity_id: str, observation_id: str) -> bool:
        return bool(self._checkpoints(workspace_id, activity_id, observation_id))

    @staticmethod
    def _validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
        required = set(schema.get("required", []))
        properties = schema.get("properties", {})
        if required - set(arguments):
            raise ValueError("computer-use action is missing required arguments")
        if schema.get("additionalProperties") is False and set(arguments) - set(properties):
            raise ValueError("computer-use action contains undeclared arguments")
        for name, value in arguments.items():
            declaration = properties.get(name, {})
            expected = declaration.get("type")
            valid = (
                expected is None
                or (expected == "string" and isinstance(value, str))
                or (expected == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
                or (expected == "integer" and isinstance(value, int) and not isinstance(value, bool))
                or (expected == "boolean" and isinstance(value, bool))
                or (expected == "object" and isinstance(value, dict))
                or (expected == "array" and isinstance(value, list))
            )
            if not valid:
                raise ValueError(f"computer-use argument {name} has the wrong type")
            if "enum" in declaration and value not in declaration["enum"]:
                raise ValueError(f"computer-use argument {name} is outside its enum")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if "minimum" in declaration and value < declaration["minimum"]:
                    raise ValueError(f"computer-use argument {name} is below its minimum")
                if "exclusiveMinimum" in declaration and value <= declaration["exclusiveMinimum"]:
                    raise ValueError(f"computer-use argument {name} is below its exclusive minimum")
                if "maximum" in declaration and value > declaration["maximum"]:
                    raise ValueError(f"computer-use argument {name} exceeds its maximum")

    def create_intent(self, workspace_id: str, actor: str, activity_id: str, request: ComputerUseIntentRequest) -> dict[str, Any]:
        activity = self.get_activity(workspace_id, activity_id)
        if activity["state"] != "active" or datetime.fromisoformat(activity["expires_at"]) < datetime.now(timezone.utc):
            raise ValueError("computer-use activity is not active")
        duplicate = next((
            entry for entry in self.store.list_editorial_records(
                kind="computer_use_intent", workspace_id=workspace_id,
            )
            if entry["activity_id"] == activity_id and entry["request_id"] == request.request_id
        ), None)
        if duplicate:
            raise ValueError("computer-use request ID was already used; execution tickets are not replayed")
        if not activity.get("profile_id"):
            raise ValueError("computer-use actions require an installed profile")
        before = self._get(request.before_observation_id, "computer_use_observation")
        if before["workspace_id"] != workspace_id or before["activity_id"] != activity_id:
            raise ValueError("before observation belongs to another activity")
        profile = self._profile(workspace_id, activity["profile_id"], activity.get("profile_version"))["profile"]
        action = next((entry for entry in profile["actions"] if entry["action_id"] == request.action_id), None)
        if action is None:
            raise ValueError("computer-use action is not declared by the profile")
        if action["safety_class"] not in {"read", "safe_reversible"}:
            raise ValueError("computer-use action requires a stronger human authority path")
        if action["route"] == "observer_only":
            raise ValueError("observer-only profile entries cannot create execution intents")
        if action["required_scope"] != "computer_use:act":
            raise ValueError("v1 computer-use actions must use the computer_use:act scope")
        if action["route"] == "canonical_command":
            context = request.context_ref
            if context is None or context.kind != "project" or request.expected_project_revision is None:
                raise ValueError("canonical computer-use actions require an exact project revision")
            if context.revision != request.expected_project_revision:
                raise ValueError("computer-use context revision does not match expected project revision")
        binding = next((entry for entry in before["bindings"] if entry["binding_id"] == request.target_binding_id), None)
        if binding is None or binding["entity_id"] not in action["entity_ids"] or request.action_id not in binding["eligible_action_ids"]:
            raise ValueError("computer-use target binding is not eligible for the requested action")
        self._validate_arguments(action.get("arguments_schema", {}), request.arguments)
        if action["checkpoint_policy"] == "before_after_required" and not self._has_checkpoint(
            workspace_id, activity_id, request.before_observation_id,
        ):
            raise ValueError("this action requires an explicit before checkpoint")
        ticket = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
        saved = self._put(workspace_id, "computer_use_intent", {
            "schema_version": COMPUTER_USE_SCHEMA_VERSION, "workspace_id": workspace_id,
            "activity_id": activity_id, "actor": actor, **request.model_dump(mode="json"),
            "route": action["route"], "safety_class": action["safety_class"],
            "profile_id": activity["profile_id"], "profile_version": activity["profile_version"],
            "profile_sha256": activity["profile_sha256"],
            "required_scope": action["required_scope"], "effect_predicates": action["effect_predicates"],
            "compensation_action_id": action.get("compensation_action_id"),
            "checkpoint_policy": action["checkpoint_policy"],
            "ticket_hash": hashlib.sha256(ticket.encode()).hexdigest(),
            "state": "authorized", "created_at": utc_now(),
        })
        # The bearer-like execution ticket is returned once and never persisted.
        return {**saved, "ticket": ticket}

    def execute(self, workspace_id: str, actor: str, intent_id: str, request: ComputerUseExecutionRequest) -> dict[str, Any]:
        intent = self._get(intent_id, "computer_use_intent")
        if intent["workspace_id"] != workspace_id or intent["state"] != "authorized":
            raise ValueError("computer-use intent is not executable")
        if hashlib.sha256(request.ticket.encode()).hexdigest() != intent["ticket_hash"]:
            raise ValueError("computer-use execution ticket is invalid")
        before = self._get(intent["before_observation_id"], "computer_use_observation")
        underlying = None
        status = "awaiting_extension"
        if intent["route"] == "canonical_command":
            context = intent.get("context_ref")
            project_id = context.get("id") if context and context.get("kind") == "project" else None
            if not project_id or not self.store.project_in_workspace(project_id, workspace_id):
                raise ValueError("canonical computer-use actions require a project in the paired workspace")
            command = intent["action_id"]
            declaration = COMMAND_REGISTRY.get(command)
            if declaration is None or declaration.safety_class != "safe_reversible":
                raise ValueError("canonical computer-use action is not safe reversible")
            receipt = self.commands.execute(project_id, CommandRequest(
                command=command, arguments=intent["arguments"],
                expected_revision=int(intent.get("expected_project_revision") or 0),
                request_id=f"computer-use-{intent['request_id']}", actor=actor,
            ), scopes=[declaration.required_scope])
            underlying = receipt.model_dump(mode="json")
            if receipt.status.value == "denied":
                raise ValueError("canonical computer-use action was denied")
            status = "awaiting_effect"
        execution = self._put(workspace_id, "computer_use_execution", {
            "schema_version": COMPUTER_USE_SCHEMA_VERSION, "workspace_id": workspace_id,
            "activity_id": intent["activity_id"], "intent_id": intent_id, "actor": actor,
            "route": intent["route"], "before_state_hash": before["application_state_hash"],
            "underlying_receipt": underlying, "state": status, "started_at": utc_now(),
        })
        self._put(workspace_id, "computer_use_intent", {
            **{key: value for key, value in intent.items() if key not in {"revision"}},
            "state": "executed", "execution_id": execution["id"], "executed_at": utc_now(),
        }, record_id=intent_id, expected_revision=int(intent["revision"]), append_only=False)
        return execution

    def complete(self, workspace_id: str, execution_id: str, request: ComputerUseCompletionRequest) -> dict[str, Any]:
        execution = self._get(execution_id, "computer_use_execution")
        if execution["workspace_id"] != workspace_id or execution["state"] not in {"awaiting_extension", "awaiting_effect"}:
            raise ValueError("computer-use execution is not awaiting an effect")
        intent = self._get(execution["intent_id"], "computer_use_intent")
        before = self._get(intent["before_observation_id"], "computer_use_observation")
        after = self._get(request.after_observation_id, "computer_use_observation")
        if after["workspace_id"] != workspace_id:
            raise ValueError("after observation belongs to another workspace")
        if intent.get("checkpoint_policy") == "before_after_required" and not self._has_checkpoint(
            workspace_id, execution["activity_id"], request.after_observation_id,
        ):
            raise ValueError("this action requires an explicit after checkpoint")
        checks: list[dict[str, Any]] = []
        same_activity = after["activity_id"] == execution["activity_id"] and after["origin"] == before["origin"]
        checks.append({"code": "activity_and_origin", "passed": same_activity})
        for predicate in intent.get("effect_predicates", []):
            passed = True
            if predicate == "state_hash_changed":
                passed = before["application_state_hash"] != after["application_state_hash"]
            elif predicate == "canonical_revision_increment":
                underlying = execution.get("underlying_receipt") or {}
                expected = underlying.get("project_revision")
                passed = any(ref.get("kind") == "project" and ref.get("id") == underlying.get("project_id") and ref.get("revision") == expected for ref in after.get("context_refs", []))
            elif predicate == "target_visible":
                target = intent["target_binding_id"]
                before_binding = next((entry for entry in before["bindings"] if entry["binding_id"] == target), None)
                passed = bool(before_binding and any(entry["entity_id"] == before_binding["entity_id"] and entry.get("visible", True) for entry in after["bindings"]))
            elif predicate == "target_selected":
                passed = bool(request.observed_effect.get("target_selected"))
            checks.append({"code": predicate, "passed": passed})
        passed = request.success and all(entry["passed"] for entry in checks)
        status = "observed_success" if passed else "observed_failure"
        receipt_body = {
            "schema_version": COMPUTER_USE_SCHEMA_VERSION, "workspace_id": workspace_id,
            "activity_id": execution["activity_id"], "intent_id": intent["id"],
            "execution_id": execution_id, "status": status,
            "before_observation_id": before["id"], "before_observation_hash": before["observation_hash"],
            "after_observation_id": after["id"], "after_observation_hash": after["observation_hash"],
            "before_checkpoint_ids": [
                entry["id"] for entry in self._checkpoints(
                    workspace_id, execution["activity_id"], before["id"],
                )
            ],
            "after_checkpoint_ids": [
                entry["id"] for entry in self._checkpoints(
                    workspace_id, execution["activity_id"], after["id"],
                )
            ],
            "profile_id": intent.get("profile_id"), "profile_version": intent.get("profile_version"),
            "profile_sha256": intent.get("profile_sha256"),
            "action_id": intent["action_id"], "route": intent["route"],
            "checks": checks, "observed_effect": request.observed_effect,
            "findings": request.findings, "verification_failure_domain": "same_extension_adapter",
            "underlying_receipt_id": (execution.get("underlying_receipt") or {}).get("id"),
            "compensation_action_id": intent.get("compensation_action_id"), "created_at": utc_now(),
        }
        receipt_body["receipt_sha256"] = _digest(receipt_body)
        receipt = self._put(workspace_id, "computer_use_receipt", receipt_body)
        self._put(workspace_id, "computer_use_execution", {
            **{key: value for key, value in execution.items() if key not in {"revision"}},
            "state": status, "receipt_id": receipt["id"], "completed_at": utc_now(),
        }, record_id=execution_id, expected_revision=int(execution["revision"]), append_only=False)
        return receipt

    def get_receipt(self, workspace_id: str, receipt_id: str) -> dict[str, Any]:
        receipt = self._get(receipt_id, "computer_use_receipt")
        if receipt["workspace_id"] != workspace_id:
            raise ValueError("computer-use receipt belongs to another workspace")
        return receipt

    def list_receipts(self, workspace_id: str) -> list[dict[str, Any]]:
        return self.store.list_editorial_records(kind="computer_use_receipt", workspace_id=workspace_id)

    def get_checkpoint(self, workspace_id: str, checkpoint_id: str) -> dict[str, Any]:
        checkpoint = self._get(checkpoint_id, "computer_use_checkpoint")
        if checkpoint["workspace_id"] != workspace_id:
            raise ValueError("computer-use checkpoint belongs to another workspace")
        return checkpoint

    def checkpoint_path(self, workspace_id: str, checkpoint_id: str) -> Path:
        checkpoint = self.get_checkpoint(workspace_id, checkpoint_id)
        return self.storage.materialize(
            StorageLocator(**checkpoint["storage"]), identity=checkpoint_id,
            expected_sha256=checkpoint["canonical_sha256"],
        )

    def create_checkpoint(self, workspace_id: str, activity_id: str, observation_id: str, source: Path, claimed_mime: str, redaction_state: str) -> dict[str, Any]:
        activity = self.get_activity(workspace_id, activity_id)
        if activity["state"] != "active" or datetime.fromisoformat(activity["expires_at"]) < datetime.now(timezone.utc):
            raise ValueError("computer-use activity is not active")
        observation = self._get(observation_id, "computer_use_observation")
        if observation["workspace_id"] != workspace_id or observation["activity_id"] != activity_id or redaction_state not in {"redacted", "not_applicable"}:
            raise ValueError("checkpoint observation or redaction state is invalid")
        if source.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("computer-use checkpoint exceeds 32 MiB")
        incoming = hashlib.sha256(source.read_bytes()).hexdigest()
        with Image.open(source) as image:
            if getattr(image, "n_frames", 1) != 1 or image.width > 8192 or image.height > 8192 or image.width * image.height > 40_000_000:
                raise ValueError("computer-use checkpoint image dimensions are unsafe")
            expected = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}.get(claimed_mime)
            if expected is None or image.format != expected:
                raise ValueError("computer-use checkpoint MIME does not match decoded image")
            image.load()
            canonical_image = ImageOps.exif_transpose(image).convert("RGB")
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temporary:
                canonical_path = Path(temporary.name)
            try:
                canonical_image.save(canonical_path, format="PNG", optimize=True)
                canonical = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
                checkpoint_id = f"computer_use_checkpoint_{uuid4().hex[:16]}"
                stored = self.storage.put_immutable(
                    canonical_path, workspace_id=workspace_id, project_id="computer_use",
                    identity=checkpoint_id, category="checkpoints", content_type="image/png",
                    expected_sha256=canonical,
                )
            finally:
                canonical_path.unlink(missing_ok=True)
        now = datetime.now(timezone.utc)
        return self._put(workspace_id, "computer_use_checkpoint", {
            "schema_version": COMPUTER_USE_SCHEMA_VERSION, "workspace_id": workspace_id,
            "activity_id": activity_id, "observation_id": observation_id,
            "incoming_sha256": incoming, "canonical_sha256": canonical,
            "mime_type": "image/png", "width": canonical_image.width, "height": canonical_image.height,
            "redaction_state": redaction_state,
            "storage": {"backend": stored.locator.backend, "namespace": stored.locator.namespace, "key": stored.locator.key, "version": stored.locator.version},
            "created_at": now.isoformat(), "expires_at": (now + timedelta(days=30)).isoformat(),
        }, record_id=checkpoint_id)

    def attach(self, workspace_id: str, activity_id: str, request: ComputerUseAttachmentRequest) -> dict[str, Any]:
        self.get_activity(workspace_id, activity_id)
        if request.context.kind == "project" and not self.store.project_in_workspace(request.context.id, workspace_id):
            raise ValueError("attachment project belongs to another workspace")
        with self.store.transaction():
            for checkpoint_id in request.checkpoint_ids:
                checkpoint = self._get(checkpoint_id, "computer_use_checkpoint")
                if checkpoint["workspace_id"] != workspace_id or checkpoint["activity_id"] != activity_id:
                    raise ValueError("checkpoint belongs to another activity")
                self._put(workspace_id, "computer_use_checkpoint", {
                    **{key: value for key, value in checkpoint.items() if key not in {"revision"}},
                    "expires_at": None, "retained_by_context": request.context.model_dump(mode="json"),
                }, record_id=checkpoint_id, expected_revision=int(checkpoint["revision"]), append_only=False)
            return self._put(workspace_id, "computer_use_attachment", {
                "schema_version": COMPUTER_USE_SCHEMA_VERSION, "workspace_id": workspace_id,
                "activity_id": activity_id, "checkpoint_ids": request.checkpoint_ids,
                "context": request.context.model_dump(mode="json"), "created_at": utc_now(),
            })


def computer_use_schemas() -> dict[str, Any]:
    return {model.__name__: model.model_json_schema() for model in (
        ComputerUseProfile, ComputerUseActivityRequest, ComputerUseActivityStateRequest,
        ComputerUseObservationRequest,
        ComputerUseIntentRequest, ComputerUseExecutionRequest, ComputerUseCompletionRequest,
        ComputerUseAttachmentRequest,
    )}
