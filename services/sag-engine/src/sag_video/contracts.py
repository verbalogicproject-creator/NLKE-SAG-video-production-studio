from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field


class CommandDeclaration(BaseModel):
    name: str
    version: int = 1
    description: str
    arguments_schema: dict[str, Any]
    handler_key: str
    entity_types: list[str]
    active_when: str
    required_scope: str = "project:write"
    safety_class: Literal[
        "read", "safe_reversible", "costed_reversible", "destructive_confirmation",
        "human_approval_only", "browser_permission_only", "credential_admin_only", "ineligible",
    ] = "safe_reversible"
    confirmation_policy: Literal["none", "exact_human_confirmation", "human_only"] = "none"
    eligible_surfaces: list[str] = Field(default_factory=lambda: ["studio", "mcp", "cli", "test"])
    ineligible_reason: str | None = None
    read_only: bool = False
    reversible: bool = True
    compensatable: bool = True
    destructive: bool = False
    revision_behavior: str = "exact_expected_revision_then_increment"
    idempotency: str = "project_id_and_request_id"
    effect: dict[str, Any] = Field(default_factory=dict)
    source_hash: str = ""

    @property
    def stable_id(self) -> str:
        return self.name

    def with_hash(self) -> "CommandDeclaration":
        body = self.model_dump(mode="json", exclude={"source_hash"})
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"source_hash": digest})


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


COMMAND_REGISTRY: dict[str, CommandDeclaration] = {
    declaration.name: declaration
    for declaration in [
        CommandDeclaration(
            name="timeline.insert_asset",
            handler_key="insert_asset",
            description="Insert one observed-valid managed asset on a compatible canonical track.",
            arguments_schema=_object_schema(
                {
                    "asset_id": {"type": "string", "minLength": 1},
                    "track_id": {"type": "string", "minLength": 1},
                    "start_ticks": {"type": "integer", "minimum": 0},
                    "duration_ticks": {"type": "integer", "minimum": 1},
                },
                ["asset_id"],
            ),
            entity_types=["asset", "track", "timeline_item"],
            active_when="asset is observed-valid and a compatible track exists",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.insert_protected_composite",
            handler_key="insert_protected_composite",
            description="Insert one approved evidence-bound protected screen composite at its exact reviewed revision.",
            arguments_schema=_object_schema(
                {
                    "composite_id": {"type": "string", "minLength": 1},
                    "track_id": {"type": "string", "minLength": 1},
                    "start_ticks": {"type": "integer", "minimum": 0},
                },
                ["composite_id"],
            ),
            entity_types=["protected_screen_composite", "screenshot_capture", "asset", "track", "timeline_item"],
            active_when="composite and source screenshot are approved, hash-valid, and bound to the exact project revision",
            confirmation_policy="exact_human_confirmation",
            eligible_surfaces=["studio", "cli", "test"],
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.move_item",
            handler_key="move_item",
            description="Move a stable timeline item in time or canvas space.",
            arguments_schema=_object_schema(
                {
                    "item_id": {"type": "string", "minLength": 1},
                    "start_ticks": {"type": "integer", "minimum": 0},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "magnetic": {"type": "boolean"},
                    "snap_threshold_ticks": {"type": "integer", "minimum": 0, "maximum": 1200000},
                    "ripple": {"type": "boolean"},
                },
                ["item_id"],
            ),
            entity_types=["timeline_item"],
            active_when="target item exists in the current project revision",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.trim_clip",
            handler_key="trim_clip",
            description="Trim either clip edge, including its timeline start and bounded source range.",
            arguments_schema=_object_schema(
                {
                    "item_id": {"type": "string", "minLength": 1},
                    "start_ticks": {"type": "integer", "minimum": 0},
                    "duration_ticks": {"type": "integer", "minimum": 1},
                    "source_in_ticks": {"type": "integer", "minimum": 0},
                    "source_out_ticks": {"type": "integer", "minimum": 1},
                    "trim_start_ticks": {"type": "integer", "minimum": 0},
                    "trim_end_ticks": {"type": "integer", "minimum": 0},
                    "ripple": {"type": "boolean"},
                },
                ["item_id", "duration_ticks"],
            ),
            entity_types=["timeline_item", "asset"],
            active_when="target is a video or audio item",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.split_clip",
            handler_key="split_clip",
            description="Split one video or audio item at an exact timeline tick.",
            arguments_schema=_object_schema(
                {
                    "item_id": {"type": "string", "minLength": 1},
                    "at_ticks": {"type": "integer", "minimum": 1},
                },
                ["item_id", "at_ticks"],
            ),
            entity_types=["timeline_item"],
            active_when="target is video/audio and split lies strictly inside it",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.delete_item",
            handler_key="delete_item",
            description="Delete one stable timeline item from its track.",
            arguments_schema=_object_schema(
                {
                    "item_id": {"type": "string", "minLength": 1},
                    "ripple": {"type": "boolean"},
                },
                ["item_id"],
            ),
            entity_types=["timeline_item"],
            active_when="target item exists",
            destructive=True,
            safety_class="destructive_confirmation",
            confirmation_policy="exact_human_confirmation",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.set_clip_transform",
            handler_key="set_clip_transform",
            description="Set fit, scale, position, opacity, or rotation on a visual clip.",
            arguments_schema=_object_schema(
                {
                    "item_id": {"type": "string", "minLength": 1},
                    "fit_mode": {"type": "string", "enum": ["fit", "fill", "stretch"]},
                    "scale": {"type": "number", "exclusiveMinimum": 0, "maximum": 20},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "opacity": {"type": "number", "minimum": 0, "maximum": 1},
                    "rotation": {"type": "number", "minimum": -360, "maximum": 360},
                },
                ["item_id"],
            ),
            entity_types=["timeline_item"],
            active_when="target is video or image",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.set_audio_gain",
            handler_key="set_audio_gain",
            description="Set bounded gain and mute state on an audio-bearing item.",
            arguments_schema=_object_schema(
                {
                    "item_id": {"type": "string", "minLength": 1},
                    "gain_db": {"type": "number", "minimum": -60, "maximum": 24},
                    "muted": {"type": "boolean"},
                },
                ["item_id"],
            ),
            entity_types=["timeline_item"],
            active_when="target is video or audio",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.create_title",
            handler_key="create_title",
            description="Create a timed title card on the canonical overlay track.",
            arguments_schema=_object_schema(
                {
                    "text": {"type": "string", "minLength": 1, "maxLength": 500},
                    "track_id": {"type": "string", "minLength": 1},
                    "start_ticks": {"type": "integer", "minimum": 0},
                    "duration_ticks": {"type": "integer", "minimum": 1},
                    "x": {"type": "integer"}, "y": {"type": "integer"},
                    "width": {"type": "integer", "minimum": 1},
                    "height": {"type": "integer", "minimum": 1},
                    "color": {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"},
                },
                ["text", "start_ticks", "duration_ticks"],
            ),
            entity_types=["track", "timeline_item", "title"],
            active_when="a canonical overlay track exists",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.set_title",
            handler_key="set_title",
            description="Set the text of a title item.",
            arguments_schema=_object_schema(
                {
                    "item_id": {"type": "string", "minLength": 1},
                    "text": {"type": "string", "minLength": 1, "maxLength": 500},
                },
                ["item_id", "text"],
            ),
            entity_types=["timeline_item"],
            active_when="target is a title item",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.set_title_transform",
            handler_key="set_title_transform",
            description="Set the canvas position and dimensions of a title item.",
            arguments_schema=_object_schema(
                {
                    "item_id": {"type": "string", "minLength": 1},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "width": {"type": "integer", "minimum": 1},
                    "height": {"type": "integer", "minimum": 1},
                    "color": {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"},
                },
                ["item_id"],
            ),
            entity_types=["timeline_item"],
            active_when="target is a title item",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.set_caption_style",
            handler_key="set_caption_style",
            description="Apply a validated dynamic-caption preset and visual controls.",
            arguments_schema=_object_schema(
                {
                    "item_id": {"type": "string"},
                    "preset": {"type": "string", "enum": ["bold_pop", "clean", "minimal"]},
                    "font_family": {"type": "string"}, "font_size": {"type": "integer", "minimum": 16, "maximum": 160},
                    "text_color": {"type": "string"}, "highlight_color": {"type": "string"},
                    "background_color": {"type": "string"}, "position": {"type": "string", "enum": ["top", "middle", "bottom"]},
                    "words_per_cue": {"type": "integer", "minimum": 1, "maximum": 12},
                }, ["item_id"],
            ), entity_types=["timeline_item", "caption"], active_when="target is a caption item",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.set_caption_words",
            handler_key="set_caption_words",
            description="Replace editable, word-timed caption content.",
            arguments_schema=_object_schema({"item_id": {"type": "string"}, "words": {"type": "array", "items": {"type": "object"}}}, ["item_id", "words"]),
            entity_types=["timeline_item", "caption"], active_when="target is a caption item",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.set_crop_keyframes",
            handler_key="set_crop_keyframes",
            description="Replace the time-varying crop path for a video or image item.",
            arguments_schema=_object_schema({"item_id": {"type": "string"}, "keyframes": {"type": "array", "minItems": 1, "items": {"type": "object"}}}, ["item_id", "keyframes"]),
            entity_types=["timeline_item", "crop_keyframe"], active_when="target is a video or image item",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="project.rename",
            handler_key="rename",
            description="Rename the canonical project while preserving its stable identity.",
            arguments_schema=_object_schema(
                {"name": {"type": "string", "minLength": 1, "maxLength": 120}},
                ["name"],
            ),
            entity_types=["project"],
            active_when="the project exists at the expected revision",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="project.undo",
            handler_key="undo",
            description="Create a compensating revision from the latest project event.",
            arguments_schema=_object_schema({}, []),
            entity_types=["project", "revision"],
            active_when="the project has an event that can be compensated",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="project.redo",
            handler_key="redo",
            description="Reapply the next canonical edit after a compensating undo.",
            arguments_schema=_object_schema({}, []),
            entity_types=["project", "revision"],
            active_when="the project history cursor has a later canonical edit",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
    ]
}

COMMAND_REGISTRY = {name: declaration.with_hash() for name, declaration in COMMAND_REGISTRY.items()}

APPLICATION_ACTIONS: dict[str, CommandDeclaration] = {
    entry.name: entry.with_hash()
    for entry in [
        CommandDeclaration(
            name="analysis.generate_shorts", handler_key="shorts_job",
            description="Analyze an exact source revision and propose bounded short candidates.",
            arguments_schema=_object_schema({"source_revision": {"type": "integer", "minimum": 1}}, ["source_revision"]),
            entity_types=["project", "asset", "suggestion"], active_when="an observed source asset exists",
            required_scope="analysis:run", safety_class="costed_reversible", reversible=False, compensatable=False,
            effect={"kind": "persistent_job"},
        ),
        CommandDeclaration(
            name="render.verified", handler_key="render_job",
            description="Render and independently observe one exact sequence revision.",
            arguments_schema=_object_schema({"project_revision": {"type": "integer", "minimum": 1}}, ["project_revision"]),
            entity_types=["project", "job", "artifact", "receipt"], active_when="the sequence revision is renderable",
            required_scope="render:run", safety_class="costed_reversible", reversible=False, compensatable=True,
            effect={"kind": "independently_observed_artifact"},
        ),
        CommandDeclaration(
            name="focus.shared", handler_key="shared_focus",
            description="Ask the browser to focus stable semantic timeline identities.",
            arguments_schema=_object_schema({"item_ids": {"type": "array", "items": {"type": "string"}}}, ["item_ids"]),
            entity_types=["timeline_item"], active_when="the target identities exist",
            required_scope="focus:write", effect={"kind": "browser_observed_effect"},
        ),
        CommandDeclaration(
            name="media.upload", handler_key="browser_upload",
            description="Import a human-selected local media file.", arguments_schema=_object_schema({}, []),
            entity_types=["asset"], active_when="a human selects a local file",
            required_scope="media:upload", safety_class="browser_permission_only", confirmation_policy="human_only",
            eligible_surfaces=["studio"], ineligible_reason="Codex cannot select or upload a local file.",
            reversible=False, compensatable=False,
        ),
        CommandDeclaration(
            name="capture.start", handler_key="browser_capture",
            description="Start an explicit human-approved browser media capture.", arguments_schema=_object_schema({}, []),
            entity_types=["capture_session", "asset"], active_when="the browser supports the requested device capture",
            required_scope="capture:start", safety_class="browser_permission_only", confirmation_policy="human_only",
            eligible_surfaces=["studio"], ineligible_reason="Browser device permission requires a human gesture.",
            reversible=False, compensatable=False,
        ),
        CommandDeclaration(
            name="connection.oauth", handler_key="oauth_connect",
            description="Connect a publishing account through its official OAuth flow.", arguments_schema=_object_schema({}, []),
            entity_types=["platform_connection"], active_when="a supported official provider is selected",
            required_scope="connections:admin", safety_class="credential_admin_only", confirmation_policy="human_only",
            eligible_surfaces=["studio"], ineligible_reason="Codex cannot grant OAuth or manage credentials.",
            reversible=False, compensatable=True,
        ),
        CommandDeclaration(
            name="release.approve", handler_key="release_approval",
            description="Human-approve an immutable revision, artifact, metadata, and destination bundle.",
            arguments_schema=_object_schema({"bundle_hash": {"type": "string"}}, ["bundle_hash"]),
            entity_types=["release_approval"], active_when="all artifacts are independently observed",
            required_scope="release:approve", safety_class="human_approval_only", confirmation_policy="human_only",
            eligible_surfaces=["studio"], ineligible_reason="Release approval is human-only.", reversible=False, compensatable=True,
        ),
        CommandDeclaration(
            name="publish.dispatch_approved", handler_key="publication_dispatch",
            description="Dispatch destination jobs for an existing exact human-approved bundle.",
            arguments_schema=_object_schema({"approval_id": {"type": "string"}}, ["approval_id"]),
            entity_types=["release_approval", "publication_attempt"], active_when="the bound approval is active and unchanged",
            required_scope="release:prepare", safety_class="costed_reversible", reversible=False, compensatable=True,
            effect={"kind": "external_platform_acknowledgement"},
        ),
        *[
            CommandDeclaration(
                name=name,
                handler_key=name.removeprefix("spatial.") + "_directive",
                description=description,
                arguments_schema=_object_schema(
                    {"target_ids": {"type": "array", "items": {"type": "string"}}},
                    [],
                ),
                entity_types=["spatial_entity", "viewport"],
                active_when="a Studio browser consumer is connected and spatial directives are not paused",
                required_scope="focus:write",
                safety_class="safe_reversible",
                eligible_surfaces=["studio", "mcp", "test"],
                effect={"kind": "browser_observed_effect", "ack_required": True},
            )
            for name, description in (
                ("spatial.focus_entity", "Focus an exact stable semantic entity."),
                ("spatial.frame_entity", "Frame an exact stable semantic entity in the active renderer."),
                ("spatial.isolate_neighborhood", "Isolate the bounded causal neighborhood of a stable entity."),
                ("spatial.reveal_dependencies", "Reveal bounded upstream dependencies for a stable entity."),
                ("spatial.reveal_blast_radius", "Reveal bounded downstream effects for a stable entity."),
                ("spatial.set_depth", "Switch to an explicit Edit, Context, or System depth."),
                ("spatial.reset_view", "Reset browser-local spatial viewport state."),
            )
        ],
    ]
}


def registry_hash() -> str:
    combined = {**COMMAND_REGISTRY, **APPLICATION_ACTIONS}
    body = [combined[name].model_dump(mode="json") for name in sorted(combined)]
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def declared_commands() -> list[dict[str, Any]]:
    return [
        {"stable_id": name, **COMMAND_REGISTRY[name].model_dump(mode="json")}
        for name in sorted(COMMAND_REGISTRY)
    ]


def declared_actions() -> list[dict[str, Any]]:
    combined = {**COMMAND_REGISTRY, **APPLICATION_ACTIONS}
    return [{"stable_id": name, **combined[name].model_dump(mode="json")} for name in sorted(combined)]


def validate_action_coverage(command_handlers: dict[str, str], application_handler_keys: set[str]) -> None:
    declared_command_names = set(COMMAND_REGISTRY)
    if set(command_handlers) != declared_command_names:
        missing = sorted(declared_command_names - set(command_handlers))
        extra = sorted(set(command_handlers) - declared_command_names)
        raise RuntimeError(f"command registry coverage mismatch: missing={missing}, extra={extra}")
    for name, declaration in COMMAND_REGISTRY.items():
        if command_handlers[name] != f"_{declaration.handler_key}":
            raise RuntimeError(f"command handler mismatch: {name}")
    missing_actions = sorted(
        name for name, declaration in APPLICATION_ACTIONS.items()
        if declaration.handler_key not in application_handler_keys
    )
    if missing_actions:
        raise RuntimeError(f"application action coverage mismatch: missing={missing_actions}")
