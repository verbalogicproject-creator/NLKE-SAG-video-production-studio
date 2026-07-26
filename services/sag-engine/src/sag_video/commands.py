from __future__ import annotations

from typing import Any
from uuid import uuid4

from .contracts import COMMAND_REGISTRY
from .models import (
    CommandBatchRequest,
    CommandProposalRequest,
    CommandRequest,
    CommandValidationError,
    CaptionStyle,
    CaptionWord,
    CropKeyframe,
    Project,
    Receipt,
    ReceiptStatus,
    StaleRevisionError,
    utc_now,
)
from .store import Store


class CommandService:
    HANDLERS = {
        "timeline.insert_asset": "_insert_asset",
        "timeline.move_item": "_move_item",
        "timeline.trim_clip": "_trim_clip",
        "timeline.split_clip": "_split_clip",
        "timeline.delete_item": "_delete_item",
        "timeline.set_clip_transform": "_set_clip_transform",
        "timeline.set_audio_gain": "_set_audio_gain",
        "timeline.set_title": "_set_title",
        "timeline.set_title_transform": "_set_title_transform",
        "timeline.set_caption_style": "_set_caption_style",
        "timeline.set_caption_words": "_set_caption_words",
        "timeline.set_crop_keyframes": "_set_crop_keyframes",
        "project.undo": "_undo",
        "project.redo": "_redo",
    }

    def __init__(self, store: Store):
        self.store = store

    @staticmethod
    def _scope_allowed(scopes: list[str], required: str) -> bool:
        return "*" in scopes or required in scopes

    def _denied(self, project_id: str, request: CommandRequest, revision: int, reason: str) -> Receipt:
        return self.store.create_receipt(
            project_id=project_id, command=request.command, status=ReceiptStatus.DENIED,
            request_id=request.request_id, actor=request.actor, project_revision=revision,
            payload={"reason": reason},
        )

    def _authorize(
        self, project_id: str, request: CommandRequest, declaration, scopes: list[str]
    ) -> str | None:
        if not self._scope_allowed(scopes, declaration.required_scope):
            return f"missing required scope: {declaration.required_scope}"
        if declaration.safety_class in {"human_approval_only", "browser_permission_only", "credential_admin_only", "ineligible"}:
            return declaration.ineligible_reason or f"action is {declaration.safety_class}"
        if declaration.confirmation_policy == "exact_human_confirmation" and not self.store.consume_confirmation(
            request.confirmation_id, project_id, request.command, request.arguments, request.expected_revision
        ):
            return "exact human confirmation is required for these arguments and revision"
        return None

    def _handler(self, command: str):
        declaration = COMMAND_REGISTRY[command]
        allowed = self.HANDLERS.get(command)
        if allowed != f"_{declaration.handler_key}":
            raise CommandValidationError(f"registry handler mismatch for {command}")
        return getattr(self, allowed)

    def _apply(self, project: Project, command: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handler = self._handler(command)
        return handler(project, arguments)

    def execute(
        self, project_id: str, request: CommandRequest, *, scopes: list[str] | None = None
    ) -> Receipt:
        scopes = scopes or ["*"]
        with self.store.transaction():
            duplicate = self.store.receipt_for_request(project_id, request.request_id)
            if duplicate:
                return duplicate

            project = self.store.get_project_for_update(project_id)
            if request.expected_revision != project.revision:
                raise StaleRevisionError(request.expected_revision, project.revision)

            if request.command not in COMMAND_REGISTRY or request.command not in self.HANDLERS:
                return self._denied(project_id, request, project.revision, "unknown or undeclared command")
            declaration = COMMAND_REGISTRY[request.command]
            denied_reason = self._authorize(project_id, request, declaration, scopes)
            if denied_reason:
                return self._denied(project_id, request, project.revision, denied_reason)

            before = project.model_copy(deep=True)
            after = project.model_copy(deep=True)
            observation: dict[str, Any]

            observation = self._apply(after, request.command, request.arguments)

            after.revision = before.revision + 1
            after.updated_at = utc_now()
            with self.store.transaction():
                self.store.put_project(after)
                self.store.append_event(
                    before=before,
                    after=after,
                    request_id=request.request_id,
                    actor=request.actor,
                    command=request.command,
                    arguments=request.arguments,
                )
                receipt = self.store.create_receipt(
                    project_id=project_id,
                    command=request.command,
                    status=ReceiptStatus.COMMITTED,
                    request_id=request.request_id,
                    actor=request.actor,
                    project_revision=after.revision,
                    payload={
                        "before_revision": before.revision,
                        "after_revision": after.revision,
                        "verification": {
                            "kind": "canonical_revision_readback",
                            "independent_failure_domain": False,
                            **observation,
                        },
                        # Backward-compatible payload alias. The receipt status is
                        # intentionally `committed`, not `observed_success`.
                        "observation": {
                            "kind": "canonical_revision_readback",
                            "independent_failure_domain": False,
                            **observation,
                        },
                    },
                )
            return receipt

    def propose(self, project_id: str, request: CommandProposalRequest) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        if request.expected_revision != project.revision:
            raise StaleRevisionError(request.expected_revision, project.revision)
        simulated = project.model_copy(deep=True)
        effects: list[dict[str, Any]] = []
        requirements: list[dict[str, Any]] = []
        for invocation in request.commands:
            declaration = COMMAND_REGISTRY.get(invocation.command)
            if declaration is None or invocation.command not in self.HANDLERS:
                raise CommandValidationError(f"unknown or undeclared command: {invocation.command}")
            effect = self._apply(simulated, invocation.command, invocation.arguments)
            effects.append({"command": invocation.command, "effect": effect})
            requirements.append({
                "command": invocation.command,
                "scope": declaration.required_scope,
                "safety_class": declaration.safety_class,
                "confirmation_policy": declaration.confirmation_policy,
            })
        return {
            "project_id": project_id,
            "before_revision": project.revision,
            "proposed_revision": project.revision + 1,
            "command_count": len(request.commands),
            "effects": effects,
            "requirements": requirements,
            "changes": {
                "duration_ticks": {"before": project.duration_ticks, "after": simulated.duration_ticks},
                "affected_item_ids": sorted({
                    str(invocation.arguments.get("item_id"))
                    for invocation in request.commands if invocation.arguments.get("item_id")
                }),
            },
        }

    def execute_batch(
        self, project_id: str, request: CommandBatchRequest, *, scopes: list[str] | None = None
    ) -> Receipt:
        scopes = scopes or ["*"]
        with self.store.transaction():
            duplicate = self.store.receipt_for_request(project_id, request.request_id)
            if duplicate:
                return duplicate
            project = self.store.get_project_for_update(project_id)
            if request.expected_revision != project.revision:
                raise StaleRevisionError(request.expected_revision, project.revision)
            before = project.model_copy(deep=True)
            after = project.model_copy(deep=True)
            effects: list[dict[str, Any]] = []
            destructive = [entry for entry in request.commands if COMMAND_REGISTRY.get(entry.command) and COMMAND_REGISTRY[entry.command].confirmation_policy != "none"]
            if len(destructive) > 1:
                raise CommandValidationError("a batch may contain at most one confirmation-bound command")
            for invocation in request.commands:
                declaration = COMMAND_REGISTRY.get(invocation.command)
                command_request = CommandRequest(
                    command=invocation.command, arguments=invocation.arguments,
                    expected_revision=request.expected_revision, request_id=request.request_id,
                    actor=request.actor, confirmation_id=request.confirmation_id,
                )
                if declaration is None or invocation.command not in self.HANDLERS:
                    return self._denied(project_id, command_request, project.revision, "unknown or undeclared command")
                reason = self._authorize(project_id, command_request, declaration, scopes)
                if reason:
                    return self._denied(project_id, command_request, project.revision, reason)
                effects.append({"command": invocation.command, "effect": self._apply(after, invocation.command, invocation.arguments)})
            after.revision = before.revision + 1
            after.updated_at = utc_now()
            self.store.put_project(after)
            arguments = {"commands": [entry.model_dump(mode="json") for entry in request.commands]}
            self.store.append_event(
                before=before, after=after, request_id=request.request_id, actor=request.actor,
                command="action.batch", arguments=arguments,
            )
            return self.store.create_receipt(
                project_id=project_id, command="action.batch", status=ReceiptStatus.COMMITTED,
                request_id=request.request_id, actor=request.actor, project_revision=after.revision,
                payload={
                    "before_revision": before.revision, "after_revision": after.revision,
                    "children": effects,
                    "verification": {"kind": "canonical_revision_readback", "independent_failure_domain": False},
                },
            )

    @staticmethod
    def _required(arguments: dict[str, Any], key: str) -> Any:
        if key not in arguments:
            raise CommandValidationError(f"missing required argument: {key}")
        return arguments[key]

    @staticmethod
    def _track_for_item(project: Project, item_id: str):
        for track in project.tracks:
            for item in track.items:
                if item.id == item_id:
                    return track, item
        raise CommandValidationError(f"unknown item: {item_id}")

    @staticmethod
    def _crop_at(keyframes: list[CropKeyframe], time_ticks: int) -> CropKeyframe:
        if not keyframes:
            return CropKeyframe(time_ticks=time_ticks)
        ordered = sorted(keyframes,key=lambda entry:entry.time_ticks)
        left = max((entry for entry in ordered if entry.time_ticks <= time_ticks),default=ordered[0])
        right = min((entry for entry in ordered if entry.time_ticks >= time_ticks),default=ordered[-1])
        mix = 0 if right.time_ticks == left.time_ticks else (time_ticks-left.time_ticks)/(right.time_ticks-left.time_ticks)
        return CropKeyframe(
            time_ticks=time_ticks,center_x=left.center_x+(right.center_x-left.center_x)*mix,
            center_y=left.center_y+(right.center_y-left.center_y)*mix,
            zoom=left.zoom+(right.zoom-left.zoom)*mix,
            confidence=min(value for value in (left.confidence,right.confidence) if value is not None) if any(value is not None for value in (left.confidence,right.confidence)) else None,
            locked=left.locked or right.locked,
        )

    def _insert_asset(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        asset_id = str(self._required(arguments, "asset_id"))
        try:
            asset = project.asset(asset_id)
        except KeyError as error:
            raise CommandValidationError(f"unknown asset: {asset_id}") from error
        if asset.intake_status != "observed_valid" or not asset.managed_uri:
            raise CommandValidationError("only observed-valid managed assets can be inserted")
        expected_track_kind = "video" if asset.kind == "video" else "audio" if asset.kind == "audio" else None
        if expected_track_kind is None:
            raise CommandValidationError("only video and audio assets are insertable in this phase")
        requested_track = arguments.get("track_id")
        track = next(
            (
                candidate
                for candidate in project.tracks
                if candidate.kind == expected_track_kind and (requested_track is None or candidate.id == requested_track)
            ),
            None,
        )
        if track is None:
            raise CommandValidationError(f"no compatible {expected_track_kind} track exists")
        duration = int(asset.duration_ticks or 0)
        if duration <= 0:
            raise CommandValidationError("asset has no observed positive duration")
        default_start = max((item.start_ticks + item.duration_ticks for item in track.items), default=0)
        start = int(arguments.get("start_ticks", default_start))
        if start < 0:
            raise CommandValidationError("start_ticks must not be negative")
        from .models import TimelineItem

        item = TimelineItem(
            id=f"item_{uuid4().hex[:16]}",
            kind=expected_track_kind,
            track_id=track.id,
            name=asset.name,
            start_ticks=start,
            duration_ticks=duration,
            source_in_ticks=0,
            source_out_ticks=duration,
            asset_id=asset.id,
            color="#17213a" if expected_track_kind == "video" else "#163a35",
        )
        track.items.append(item)
        track.items.sort(key=lambda entry: (entry.start_ticks, entry.id))
        project.duration_ticks = max(project.duration_ticks, start + duration)
        return {"asset_id": asset.id, "track_id": track.id, "item_id": item.id, "start_ticks": start, "duration_ticks": duration}

    def _move_item(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        item_id = str(self._required(arguments, "item_id"))
        track, item = self._track_for_item(project, item_id)
        if "start_ticks" in arguments:
            old_start = item.start_ticks
            old_end = item.start_ticks + item.duration_ticks
            start = int(arguments["start_ticks"])
            if start < 0:
                raise CommandValidationError("item would start before the project timeline")
            if bool(arguments.get("magnetic", False)):
                threshold = int(arguments.get("snap_threshold_ticks", 2 * 120_000 // 10))
                anchors = {0}
                for candidate in track.items:
                    if candidate.id != item.id:
                        anchors.update({candidate.start_ticks, candidate.start_ticks + candidate.duration_ticks})
                possibilities = [(abs(start - anchor), anchor) for anchor in anchors]
                possibilities.extend(
                    (abs(start + item.duration_ticks - anchor), anchor - item.duration_ticks)
                    for anchor in anchors
                )
                distance, snapped = min(possibilities, key=lambda value: (value[0], value[1]))
                if distance <= threshold:
                    start = max(0, snapped)
            item.start_ticks = start
            if bool(arguments.get("ripple", False)):
                delta = start - old_start
                for candidate in track.items:
                    if candidate.id != item.id and candidate.start_ticks >= old_end:
                        candidate.start_ticks = max(0, candidate.start_ticks + delta)
                track.items.sort(key=lambda entry: (entry.start_ticks, entry.id))
            project.duration_ticks = max(project.duration_ticks, start + item.duration_ticks)
        if "x" in arguments:
            item.x = int(arguments["x"])
        if "y" in arguments:
            item.y = int(arguments["y"])
        return {
            "item_id": item.id, "start_ticks": item.start_ticks, "x": item.x, "y": item.y,
            "magnetic": bool(arguments.get("magnetic", False)), "ripple": bool(arguments.get("ripple", False)),
        }

    def _trim_clip(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        item_id = str(self._required(arguments, "item_id"))
        try:
            item = project.item(item_id)
        except KeyError as error:
            raise CommandValidationError(f"unknown item: {item_id}") from error
        if item.kind not in {"video", "audio"}:
            raise CommandValidationError("only video and audio items can be trimmed")
        start = int(arguments.get("start_ticks", item.start_ticks))
        duration = int(self._required(arguments, "duration_ticks"))
        if start < 0 or duration <= 0:
            raise CommandValidationError("invalid trimmed duration")
        source_in = int(arguments.get("source_in_ticks", arguments.get("trim_start_ticks", item.source_in_ticks)))
        source_out = int(arguments.get("source_out_ticks", source_in + duration))
        if source_in < 0 or source_out <= source_in or source_out - source_in < duration:
            raise CommandValidationError("invalid source range")
        if item.asset_id:
            try:
                asset = project.asset(item.asset_id)
            except KeyError as error:
                raise CommandValidationError(f"unknown asset: {item.asset_id}") from error
            if asset.duration_ticks and source_out > asset.duration_ticks:
                raise CommandValidationError("source range exceeds observed asset duration")
        old_source_in = item.source_in_ticks
        if item.crop_keyframes:
            shift = source_in-old_source_in
            start_frame = self._crop_at(item.crop_keyframes,max(0,shift)).model_copy(update={"time_ticks":0})
            end_frame = self._crop_at(item.crop_keyframes,max(0,shift)+duration).model_copy(update={"time_ticks":duration})
            middle = [entry.model_copy(update={"time_ticks":entry.time_ticks-shift}) for entry in item.crop_keyframes if shift < entry.time_ticks < shift+duration]
            item.crop_keyframes = [start_frame,*middle,end_frame]
        old_end = item.start_ticks + item.duration_ticks
        item.start_ticks = start
        item.duration_ticks = duration
        item.source_in_ticks = source_in
        item.source_out_ticks = source_out
        item.trim_start_ticks = source_in
        item.trim_end_ticks = max(0, source_out - source_in - duration)
        if bool(arguments.get("ripple", False)):
            track, _ = self._track_for_item(project, item.id)
            delta = start + duration - old_end
            for candidate in track.items:
                if candidate.id != item.id and candidate.start_ticks >= old_end:
                    candidate.start_ticks = max(0, candidate.start_ticks + delta)
            track.items.sort(key=lambda entry: (entry.start_ticks, entry.id))
        project.duration_ticks = max(project.duration_ticks, start + duration)
        return {"item_id": item.id, "start_ticks": start, "duration_ticks": duration, "source_in_ticks": source_in, "source_out_ticks": source_out}

    def _split_clip(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        item_id = str(self._required(arguments, "item_id"))
        track, item = self._track_for_item(project, item_id)
        if item.kind not in {"video", "audio"}:
            raise CommandValidationError("only video and audio items can be split")
        at_ticks = int(self._required(arguments, "at_ticks"))
        end = item.start_ticks + item.duration_ticks
        if at_ticks <= item.start_ticks or at_ticks >= end:
            raise CommandValidationError("split must lie strictly inside the item")
        left_duration = at_ticks - item.start_ticks
        right_duration = end - at_ticks
        original_source_out = item.source_out_ticks or (item.source_in_ticks + item.duration_ticks)
        split_source = item.source_in_ticks + left_duration
        right = item.model_copy(deep=True)
        right.id = f"item_{uuid4().hex[:16]}"
        right.name = f"{item.name} (split)"
        right.start_ticks = at_ticks
        right.duration_ticks = right_duration
        right.source_in_ticks = split_source
        right.source_out_ticks = original_source_out
        if item.crop_keyframes:
            split_frame = self._crop_at(item.crop_keyframes,left_duration)
            left_frames = [entry for entry in item.crop_keyframes if entry.time_ticks < left_duration]
            item.crop_keyframes = [*left_frames,split_frame]
            right_frames = [entry.model_copy(update={"time_ticks":entry.time_ticks-left_duration}) for entry in right.crop_keyframes if entry.time_ticks > left_duration]
            right.crop_keyframes = [split_frame.model_copy(update={"time_ticks":0}),*right_frames]
        item.duration_ticks = left_duration
        item.source_out_ticks = split_source
        track.items.append(right)
        track.items.sort(key=lambda entry: (entry.start_ticks, entry.id))
        return {"item_id": item.id, "new_item_id": right.id, "at_ticks": at_ticks}

    def _delete_item(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        item_id = str(self._required(arguments, "item_id"))
        track, item = self._track_for_item(project, item_id)
        track.items = [entry for entry in track.items if entry.id != item_id]
        if bool(arguments.get("ripple", False)):
            end = item.start_ticks + item.duration_ticks
            for candidate in track.items:
                if candidate.start_ticks >= end:
                    candidate.start_ticks = max(item.start_ticks, candidate.start_ticks - item.duration_ticks)
        return {"deleted_item_id": item.id, "track_id": track.id, "ripple": bool(arguments.get("ripple", False))}

    def _set_clip_transform(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        item_id = str(self._required(arguments, "item_id"))
        try:
            item = project.item(item_id)
        except KeyError as error:
            raise CommandValidationError(f"unknown item: {item_id}") from error
        if item.kind not in {"video", "image"}:
            raise CommandValidationError("only video and image items have a visual transform")
        if "fit_mode" in arguments:
            if arguments["fit_mode"] not in {"fit", "fill", "stretch"}:
                raise CommandValidationError("invalid fit_mode")
            item.fit_mode = arguments["fit_mode"]
        for field in ("x", "y"):
            if field in arguments:
                setattr(item, field, int(arguments[field]))
        for field, lower, upper in (("scale", 0, 20), ("opacity", 0, 1), ("rotation", -360, 360)):
            if field in arguments:
                value = float(arguments[field])
                invalid = (value <= lower or value > upper) if field == "scale" else (value < lower or value > upper)
                if invalid:
                    raise CommandValidationError(f"invalid {field}")
                setattr(item, field, value)
        return {"item_id": item.id, "fit_mode": item.fit_mode, "scale": item.scale, "x": item.x, "y": item.y, "opacity": item.opacity, "rotation": item.rotation}

    def _set_audio_gain(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        item_id = str(self._required(arguments, "item_id"))
        try:
            item = project.item(item_id)
        except KeyError as error:
            raise CommandValidationError(f"unknown item: {item_id}") from error
        if item.kind not in {"video", "audio"}:
            raise CommandValidationError("only video and audio items can change gain")
        if "gain_db" in arguments:
            gain = float(arguments["gain_db"])
            if gain < -60 or gain > 24:
                raise CommandValidationError("gain_db must be between -60 and 24")
            item.gain_db = gain
        if "muted" in arguments:
            item.muted = bool(arguments["muted"])
        return {"item_id": item.id, "gain_db": item.gain_db, "muted": item.muted}

    def _set_title(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        item_id = str(self._required(arguments, "item_id"))
        try:
            item = project.item(item_id)
        except KeyError as error:
            raise CommandValidationError(f"unknown item: {item_id}") from error
        if item.kind != "title":
            raise CommandValidationError("item is not a title")
        text = str(self._required(arguments, "text")).strip()
        if not text or len(text) > 500:
            raise CommandValidationError("title text must contain 1 to 500 characters")
        item.text = text
        return {"item_id": item.id, "text": item.text}

    def _set_title_transform(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        item_id = str(self._required(arguments, "item_id"))
        try:
            item = project.item(item_id)
        except KeyError as error:
            raise CommandValidationError(f"unknown item: {item_id}") from error
        if item.kind != "title":
            raise CommandValidationError("item is not a title")
        for field in ("x", "y", "width", "height"):
            if field in arguments:
                value = int(arguments[field])
                if field in {"width", "height"} and value <= 0:
                    raise CommandValidationError(f"{field} must be positive")
                setattr(item, field, value)
        return {"item_id": item.id, "x": item.x, "y": item.y, "width": item.width, "height": item.height}

    def _set_caption_style(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        item_id = str(self._required(arguments, "item_id"))
        try:
            item = project.item(item_id)
        except KeyError as error:
            raise CommandValidationError(f"unknown item: {item_id}") from error
        if item.kind != "caption":
            raise CommandValidationError("item is not a caption track item")
        current = (item.caption_style or CaptionStyle()).model_dump(mode="json")
        current.update({key: value for key, value in arguments.items() if key != "item_id"})
        try:
            item.caption_style = CaptionStyle.model_validate(current)
        except ValueError as error:
            raise CommandValidationError(f"invalid caption style: {error}") from error
        return {"item_id": item.id, "style": item.caption_style.model_dump(mode="json")}

    def _set_caption_words(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        item_id = str(self._required(arguments, "item_id"))
        try:
            item = project.item(item_id)
        except KeyError as error:
            raise CommandValidationError(f"unknown item: {item_id}") from error
        if item.kind != "caption":
            raise CommandValidationError("item is not a caption track item")
        try:
            words = [CaptionWord.model_validate(value) for value in self._required(arguments, "words")]
        except ValueError as error:
            raise CommandValidationError(f"invalid caption words: {error}") from error
        if any(word.end_ticks > item.duration_ticks for word in words):
            raise CommandValidationError("caption word lies outside the caption item")
        if any(right.start_ticks < left.start_ticks for left, right in zip(words, words[1:])):
            raise CommandValidationError("caption words must be ordered by time")
        item.caption_words = words
        item.text = " ".join(word.text for word in words)
        return {"item_id": item.id, "word_count": len(words)}

    def _set_crop_keyframes(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        item_id = str(self._required(arguments, "item_id"))
        try:
            item = project.item(item_id)
        except KeyError as error:
            raise CommandValidationError(f"unknown item: {item_id}") from error
        if item.kind != "video":
            raise CommandValidationError("crop keyframes require a video item")
        try:
            keyframes = [CropKeyframe.model_validate(value) for value in self._required(arguments, "keyframes")]
        except ValueError as error:
            raise CommandValidationError(f"invalid crop keyframes: {error}") from error
        keyframes.sort(key=lambda entry: entry.time_ticks)
        if not keyframes or keyframes[-1].time_ticks > item.duration_ticks:
            raise CommandValidationError("crop keyframes must lie inside the video item")
        item.crop_keyframes = keyframes
        item.fit_mode = "fill"
        return {"item_id": item.id, "keyframe_count": len(keyframes)}

    def _undo(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        target = self.store.previous_edit_revision(project.id)
        if target is None:
            raise CommandValidationError("nothing to undo")
        previous = self.store.get_project_revision(project.id, target)
        preserved_revision = project.revision
        project.name = previous.name
        project.canvas = previous.canvas
        project.duration_ticks = previous.duration_ticks
        project.assets = previous.assets
        project.tracks = previous.tracks
        project.revision = preserved_revision
        arguments["history_target_revision"] = target
        return {"history_target_revision": target}

    def _redo(self, project: Project, arguments: dict[str, Any]) -> dict[str, Any]:
        target = self.store.next_edit_revision(project.id)
        if target is None:
            raise CommandValidationError("nothing to redo")
        restored = self.store.get_project_revision(project.id, target)
        preserved_revision = project.revision
        project.name = restored.name
        project.canvas = restored.canvas
        project.duration_ticks = restored.duration_ticks
        project.assets = restored.assets
        project.tracks = restored.tracks
        project.revision = preserved_revision
        arguments["history_target_revision"] = target
        return {"history_target_revision": target}
