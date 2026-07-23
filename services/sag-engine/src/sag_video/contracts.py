from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CommandDeclaration(BaseModel):
    name: str
    description: str
    arguments_schema: dict[str, Any]
    entity_types: list[str]
    active_when: str
    required_scope: str = "project:write"
    approval_level: str = "none"
    read_only: bool = False
    reversible: bool = True
    compensatable: bool = True
    destructive: bool = False
    revision_behavior: str = "exact_expected_revision_then_increment"
    idempotency: str = "project_id_and_request_id"
    effect: dict[str, Any] = Field(default_factory=dict)


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
            description="Insert one observed-valid managed asset on a compatible canonical track.",
            arguments_schema=_object_schema(
                {
                    "asset_id": {"type": "string", "minLength": 1},
                    "track_id": {"type": "string", "minLength": 1},
                    "start_ticks": {"type": "integer", "minimum": 0},
                },
                ["asset_id"],
            ),
            entity_types=["asset", "track", "timeline_item"],
            active_when="asset is observed-valid and a compatible track exists",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.move_item",
            description="Move a stable timeline item in time or canvas space.",
            arguments_schema=_object_schema(
                {
                    "item_id": {"type": "string", "minLength": 1},
                    "start_ticks": {"type": "integer", "minimum": 0},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                ["item_id"],
            ),
            entity_types=["timeline_item"],
            active_when="target item exists in the current project revision",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.trim_clip",
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
                },
                ["item_id", "duration_ticks"],
            ),
            entity_types=["timeline_item", "asset"],
            active_when="target is a video or audio item",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.split_clip",
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
            description="Delete one stable timeline item from its track.",
            arguments_schema=_object_schema(
                {"item_id": {"type": "string", "minLength": 1}},
                ["item_id"],
            ),
            entity_types=["timeline_item"],
            active_when="target item exists",
            destructive=True,
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.set_clip_transform",
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
            name="timeline.set_title",
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
            description="Set the canvas position and dimensions of a title item.",
            arguments_schema=_object_schema(
                {
                    "item_id": {"type": "string", "minLength": 1},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "width": {"type": "integer", "minimum": 1},
                    "height": {"type": "integer", "minimum": 1},
                },
                ["item_id"],
            ),
            entity_types=["timeline_item"],
            active_when="target is a title item",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.set_caption_style",
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
            description="Replace editable, word-timed caption content.",
            arguments_schema=_object_schema({"item_id": {"type": "string"}, "words": {"type": "array", "items": {"type": "object"}}}, ["item_id", "words"]),
            entity_types=["timeline_item", "caption"], active_when="target is a caption item",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="timeline.set_crop_keyframes",
            description="Replace the time-varying crop path for a video item.",
            arguments_schema=_object_schema({"item_id": {"type": "string"}, "keyframes": {"type": "array", "minItems": 1, "items": {"type": "object"}}}, ["item_id", "keyframes"]),
            entity_types=["timeline_item", "crop_keyframe"], active_when="target is a video item",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
        CommandDeclaration(
            name="project.undo",
            description="Create a compensating revision from the latest project event.",
            arguments_schema=_object_schema({}, []),
            entity_types=["project", "revision"],
            active_when="the project has an event that can be compensated",
            effect={"kind": "canonical_revision_readback", "independent_failure_domain": False},
        ),
    ]
}


def declared_commands() -> list[dict[str, Any]]:
    return [COMMAND_REGISTRY[name].model_dump(mode="json") for name in sorted(COMMAND_REGISTRY)]
