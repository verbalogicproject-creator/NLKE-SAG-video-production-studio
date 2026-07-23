# SAG Video Implementation Plan

Status: active implementation source of truth; Phases 0–2, persistence, the Phase 3 functional slice, and Codex-link preparation are implemented  
Created: July 22, 2026  
Repository: `sag-video`  
Target: a functional, verified, agent-native production pipeline for technical videos

## 1. Purpose

Build SAG Video into a small but genuinely useful video-production application
that can be operated through either its browser GUI or the terminal surfaces used
by Codex and Claude Code.

The first product outcome is deliberately narrow:

> Starting with a real terminal, screen, browser, camera, or narration capture,
> produce a polished 30–60 second technical video in horizontal and vertical
> formats, verify the actual output, and hand it to a human for publishing.

SAG Video is not trying to become a general nonlinear editor in its first
versions. Its differentiator is a semantic, automatable production workflow in
which commands, renders, captures, and exports are not considered successful
until their intended effects have been observed.

### 1.1 SAG is broader than this editor

SAG Video is one declared application built with SAG, not the definition or
limit of SAG itself.

The reusable SAG proposition is:

> An application declares what exists, what is currently relevant, what actions
> are available, who may invoke them, what effect each action intends, and what
> evidence can establish the outcome. Human and agent surfaces then operate the
> same application-owned semantic state.

This means a video editor can declare clips, tracks, selections, edits, captures,
renders, and output predicates; another application could declare a different
domain without pretending its objects and effects are video concepts. SAG is
not one universal action or one receipt endpoint. It is the bounded contract
joining semantic context, authority, control, expected effects, observation,
and evidence.

The referenced ARIA SU Lab demonstrates part of this potential with a declared
function registry, context-dependent command sets, state serialization, and a
large handler surface over one visual application. SAG Video should adopt that
application-declaration pattern while strengthening it with stable identities,
server-owned state, revisions, explicit authority, expected-effect contracts,
and observations.

Codex or Claude Code supplies the reasoning as an already-running external
agent. SAG Video does not need to embed a model or hold a model-provider API key:

```text
user types to Codex/Claude Code in terminal
→ agent queries SAG application contract and current context
→ agent invokes a declared semantic command through MCP/CLI
→ application validates authority and revision
→ canonical state changes
→ GUI reflects the same state
→ observer finalizes the bounded effect receipt
```

An embedded in-GUI chat panel is optional later. It must not be faked by
silently spawning an unsupported model session or by requiring the application
to scrape a Codex interface. The first no-API-key experience is the paired
terminal agent controlling the GUI's canonical project through SAG tools.

This document is the persistent implementation source of truth. After context
compaction, begin by reading this file, `README.md`, `docs/architecture.md`, and
the current source before editing anything.

## 2. Relationship to the SAG evidence sprint

This is a product prototype track. It must not be represented as independent
customer validation, market evidence, or proof that external teams need SAG.
Any learning from building or using it is first-party product evidence and must
be labeled accordingly.

Do not modify historical SAG planning records to make them agree with this
build. If the evidence sprint proceeds in parallel, keep its participant data,
incident IDs, claims, and decision gates separate.

## 3. Current baseline

The repository implements a coherent SAG proof slice plus the first functional
editing and persistence milestones:

- FastAPI control service and migration-driven normalized SQLite repositories.
- One canonical project model with stable asset, track, and item IDs.
- Integer media time at 120,000 ticks per second.
- Revision-checked and idempotent semantic commands.
- Browser, CLI, and MCP surfaces over the same command boundary.
- Single-use pairing codes and scoped terminal tokens.
- An allowlisted FFmpeg controller.
- Render receipts that distinguish dispatch from observation.
- `ffprobe` and decoded-frame output observation.
- A separate observer-service deployment option.
- Twenty-eight passing tests after the normalized persistence gate.

The application now imports, previews, edits, renders, plays, and observes real
media. Rendering is asynchronous and persistent; video, titles, embedded audio,
and narration tracks compile through an allowlisted FFmpeg graph. The remaining
core limitations are realtime narration mixing in the browser, captions,
output-variant management, deterministic cancellation/timeout fault injection,
and longer target-phone thermal testing. The seeded demo still contains legacy
`generated://` placeholder slates, but they are truthfully marked pending and
cannot enter a verified real-media render.

## 4. Product principles

All implementation decisions must preserve these constraints.

### 4.1 One canonical project

The GUI, CLI, MCP tools, renderer, and observers use the same server-owned
project. The browser must not maintain a second authoritative timeline.

### 4.2 Semantic commands, not raw execution

Expose declared operations such as `timeline.split_clip` and
`capture.narration.start`. Never expose arbitrary shell commands, arbitrary
FFmpeg filters, or client-supplied filesystem paths to browser or agent callers.

### 4.3 Context does not grant authority

Selection and project context identify what the user is working on; they do not
authorize mutation, capture, publishing, or access to other files.

### 4.4 Dispatch is not success

Use a causal receipt for every consequential action. A successful subprocess or
HTTP response advances the receipt only to an awaiting-observation state.

### 4.5 Human gates remain real gates

Microphone use, camera use, Android screen capture, external sharing, and public
publishing require explicit user action. An agent may prepare the operation but
may not silently bypass Android consent or platform approval.

### 4.6 Local-first, worker-compatible

The initial system must work on this Android/Termux environment. Keep capture,
render, transcription, observation, storage, and publishing behind interfaces
so heavy work can later move to a desktop or cloud worker without changing the
project semantics.

### 4.7 Uncertainty never becomes success

An observer that cannot evaluate its predicate returns an inconclusive failure,
not success. Each observation discloses whether it shares a failure domain with
the controller.

### 4.8 The application declares its agent surface

Do not hand-maintain unrelated command lists in the browser, CLI, MCP server,
and controller. Define an application-owned command registry from which the
discoverable contract and supported surfaces are derived.

For every declared command, publish:

- Stable namespace/name and contract version.
- Human description and typed argument schema.
- Entity types/IDs it targets.
- Contexts/states in which it is available.
- Preconditions, required authority, and approval level.
- Whether it is read-only, reversible, compensatable, or destructive.
- Expected canonical revision behavior.
- Declared effect and observer/evidence contract when applicable.
- Timeout/cancellation/idempotency behavior.

The command registry is capability description, not capability grant. The
server remains authoritative and evaluates the actor's actual scope and current
state on every invocation.

### 4.9 Prefer semantic control over computer use

When the application owns the domain, Codex should operate stable IDs and typed
commands rather than screen coordinates, screenshots, DOM event simulation, or
natural-language labels.

Pixel/DOM computer use is a fallback for applications that expose no semantic
contract. It is weaker evidence because layout changes, hidden state, optimistic
UI, and failed event handlers can separate the gesture from the intended effect.
SAG Video must not use screenshot-and-click automation for its own editor
controls.

Visual models may still inspect user-approved frames and propose actions, but
accepted actions pass through the same semantic command and receipt boundary.

## 5. Target architecture

```text
Android picker / screen recorder / camera files
Termux microphone / asciinema terminal capture
Playwright browser capture
Future Android SAG Capture companion
                         │
                         ▼
                  capture adapters
                         │
                         ▼
     managed media intake, hash, probe, proxy, thumbnail
                         │
                         ▼
         canonical revisioned semantic timeline
              ▲          │             ▲
              │          │             │
          browser GUI   CLI        MCP agents
                         │
                         ▼
            immutable render specification
                         │
                         ▼
        allowlisted FFmpeg compiler and job runner
                         │
                         ▼
       artifact handoff by managed path and SHA-256
                         │
                         ▼
        stream, frame, audio, caption, and safety observers
                         │
                         ▼
      review → gallery/share sheet → future private upload
```

## 6. Target repository structure

Introduce the following modules incrementally. Do not create empty abstractions
far ahead of their first use.

```text
src/sag_video/
  app.py                  HTTP routes and composition only
  models.py               shared domain and API models
  repository.py           storage-neutral repository protocols and records
  migrations.py           ordered normalized SQLite schema migrations
  store.py                SQLite repository implementation and unit of work
  commands.py             semantic mutation dispatch
  jobs.py                 bounded background job runner
  media.py                intake, managed paths, probing, proxies
  timeline.py             validation and render-plan compilation helpers
  rendering.py            render service and FFmpeg argv compiler
  observer.py             composed artifact observers
  captures/
    base.py               adapter protocol and capability report
    narration.py          Termux microphone adapter
    asciinema.py          terminal-event capture adapter
    playwright.py         later browser adapter
  transcription.py        later Whisper adapter
  publishing.py           later share/upload adapters
  cli.py
  mcp_server.py
  static/
    index.html
    app.js
    styles.css
```

If a module would contain only a pass-through wrapper, leave the logic in the
existing module until the extraction creates a meaningful boundary.

## 7. Domain-model evolution

Project state is normalized in SQLite and reconstructed from exact revision
rows. Schema changes require Pydantic defaults plus separate physical database
and application schema versions. Old blob-store projects remain loadable through
the v1 migration. The complete contract is in `docs/persistence-spec.md`.

### 7.1 Asset

Extend `Asset` from a display record into a managed-media record:

- `id`: stable semantic identity.
- `kind`: video, audio, image, terminal capture, caption, or generated.
- `name`: user-facing name.
- `source_kind`: upload, Android picker, Termux microphone, asciinema,
  Playwright, Android companion, generated, or derived.
- `managed_uri`: server-created opaque media identity. Never accept this as a
  raw client filesystem path.
- `original_filename`: sanitized display metadata only.
- `sha256` and byte size.
- `mime_type`.
- `duration_ticks` when applicable.
- Video metadata: width, height, average/rational frame rate, codec, rotation.
- Audio metadata: codec, channel count, sample rate.
- `proxy_asset_id`, `thumbnail_asset_id`, and `parent_asset_id` for derived
  artifacts.
- `intake_status`: pending, observed_valid, observed_invalid.
- `observation_summary` with bounded findings.

Do not store absolute private paths in API responses. Resolve opaque managed
URIs through a server-side media store rooted under `.sag-video/media/`.

### 7.2 Timeline items

Extend `TimelineItem` only as each feature lands:

- `source_in_ticks` and `source_out_ticks` rather than ambiguous trim totals.
- Position and duration remain timeline-relative integer ticks.
- Video transform: fit mode, crop rectangle, scale, x/y, opacity, rotation.
- Audio controls: gain in dB, muted, fade-in/out ticks.
- Title/caption style: text, font family from an allowlist, font size, colors,
  background, alignment, safe-area role.
- Caption item reference to word/segment timing data.

Validate that source ranges do not exceed observed asset duration.

### 7.3 Project and output presets

Add:

- Project creation and listing rather than a hardcoded `demo` only.
- `schema_version`.
- A preview canvas and one or more output variants.
- Brand preset reference.
- Optional episode metadata: hook, topic, CTA, description draft, tags.

Initial output presets:

- `landscape_1080p`: 1920×1080, 30 fps.
- `vertical_1080p`: 1080×1920, 30 fps.
- `preview_540p`: bounded proxy resolution for phone editing.

Frame rate conversion must be explicit in the frozen render specification.

### 7.4 Jobs

Persist long-running job state separately from receipts:

- Job ID, kind, project/revision, state, progress, worker, timestamps.
- Frozen input specification.
- Result artifact IDs.
- Bounded error detail.
- Cancellation-request state.

A receipt describes the causal contract and observed outcome. A job describes
execution progress. Do not use transient in-memory tasks as the only record.

### 7.5 Capture sessions

Persist capture-session state for operations that span user actions:

- Adapter and capability snapshot.
- Requested format and duration limit.
- Consent/user-action requirement.
- `prepared`, `awaiting_user_action`, `capturing`, `stopping`,
  `artifact_written`, `awaiting_observation`, terminal state.
- Result asset ID and observation findings.

### 7.6 Suggestions

Automated cuts and reframes are immutable proposals, not direct edits:

- Suggestion ID and generator.
- Exact source project revision.
- Proposed semantic commands.
- Human-readable reason and evidence.
- Confidence without claiming correctness.
- Pending, accepted, rejected, or stale.

Accepting a suggestion executes normal revision-checked commands and records
the human/agent actor. A stale suggestion must be regenerated or explicitly
rebased.

### 7.7 SAG application contract

Add a versioned `ApplicationContract` generated from the actual semantic
registries rather than maintained as prose. It contains:

- Application identity, contract version, and supported protocol versions.
- Entity type descriptions and identity rules.
- Context projections: project, revision, selection, active variant, active
  job/capture, and current view where relevant.
- Full declared command schemas.
- Commands currently active for the requested project/context.
- Actor scope and required approvals reported separately from availability.
- Receipt states, effect/observer types, and evidence schemas.
- Capability availability such as FFmpeg, Termux microphone, terminal capture,
  transcription, and publishing adapters.

Expose both a complete contract and a compact live context. The structured JSON
is authoritative; optional natural-language summaries are derived convenience
views and must not replace stable IDs or schemas.

Initial endpoints:

- `GET /api/contract`
- `GET /api/projects/{project_id}/context`
- `GET /api/projects/{project_id}/commands/active`

Initial CLI/MCP discovery:

```text
sag-video contract show --json
sag-video context show --project ID --json
sag-video command list --project ID --active --json
```

Every advertised mutation must resolve to a real allowlisted handler. Every
allowlisted externally invocable handler must have a declaration. Add a
contract-consistency test so drift fails the test suite.

## 8. Receipt vocabulary

Keep the current render statuses and add only states required by user-gated or
long-running work.

Common nonterminal states:

- `accepted`
- `awaiting_user_action`
- `awaiting_user_consent`
- `dispatched`
- `capturing`
- `rendering`
- `artifact_written`
- `awaiting_observation`
- `awaiting_approval`

Terminal states:

- `observed_success`
- `observed_failure`
- `execution_failed`
- `denied`
- `cancelled`
- `timeout`

Do not report editing-state readback as independent observation. Continue to
label it `canonical_revision_readback` with
`independent_failure_domain: false`.

Expected causal contracts by action:

| Action | Declared effect | Required observation |
|---|---|---|
| Media intake | Source became a usable managed asset | Hash, readable streams, bounded metadata |
| Timeline edit | Exact semantic state changed | Canonical revision readback |
| Capture | Intended recording artifact was written | Hash, duration, expected streams, adapter-specific checks |
| Render | Exact revision produced target variant | Stream, duration, frame/audio/caption/safety predicates |
| Gallery export | Verified file became available to Android | Media scan/share handoff result where observable |
| Publish | Approved platform object was created | Platform response and returned object identity; never infer from upload dispatch |

## 9. API, CLI, and MCP surface

Implement endpoints and commands in the phase where their behavior becomes
real. Names below are the target contract and may be adjusted once if a concrete
implementation constraint requires it.

### 9.1 Projects

- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `GET /api/projects/{project_id}/context`
- `POST /api/projects/{project_id}/commands`
- `GET /api/projects/{project_id}/receipts`

CLI:

```text
sag-video project list
sag-video project create NAME --preset landscape_1080p
sag-video project show --project ID --json
```

Contract discovery is model-independent. Codex and Claude Code read it through
their paired CLI/MCP connection; SAG Video does not call a model provider merely
to explain its available operations.

### 9.2 Media

- `POST /api/projects/{project_id}/assets/uploads`
- `GET /api/projects/{project_id}/assets/{asset_id}`
- `GET /api/projects/{project_id}/assets/{asset_id}/proxy`
- `GET /api/projects/{project_id}/assets/{asset_id}/thumbnail`
- `DELETE /api/projects/{project_id}/assets/{asset_id}` only when unreferenced,
  with an explicit confirmation contract.

CLI:

```text
sag-video asset import FILE --project ID
sag-video asset list --project ID
sag-video asset show ASSET_ID --project ID --json
```

The CLI may read a local file selected by its user and upload its bytes. The
server must not accept a caller-supplied absolute path and read it on the
caller's behalf.

### 9.3 Timeline

Semantic command names:

- `timeline.insert_asset`
- `timeline.move_item`
- `timeline.trim_clip`
- `timeline.split_clip`
- `timeline.delete_item`
- `timeline.set_clip_transform`
- `timeline.set_audio_gain`
- `timeline.set_title`
- `timeline.set_title_transform`
- `timeline.apply_caption_style`
- `project.undo`

All require a request ID and exact expected revision.

### 9.4 Captures

- `GET /api/capabilities`
- `POST /api/projects/{project_id}/captures`
- `POST /api/captures/{capture_id}/stop`
- `GET /api/captures/{capture_id}`

CLI examples:

```text
sag-video capture capabilities --json
sag-video capture narration start --project ID --codec opus --limit 60
sag-video capture narration stop CAPTURE_ID
sag-video capture terminal prepare --project ID --geometry 100x30
```

Do not add a remote `capture sensor --all` or raw command surface. Sensor and
camera operations require a bounded adapter, a visible purpose, and explicit
user invocation.

### 9.5 Renders

- `POST /api/projects/{project_id}/renders` returns an accepted receipt and job
  promptly rather than blocking until FFmpeg completes.
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/cancel`
- `GET /api/artifacts/{artifact_id}`

CLI:

```text
sag-video render start --project ID --revision N --preset vertical_1080p
sag-video job watch JOB_ID
sag-video receipt show RECEIPT_ID --json
```

MCP should expose semantic equivalents with concise schemas. It must not expose
raw upload paths, FFmpeg arguments, shell execution, Android consent acceptance,
or public-post approval.

## 10. Ordered implementation phases

Each phase is a pause point. Run its verification and meet its acceptance gate
before proceeding. Commit or otherwise checkpoint the completed slice without
including `.sag-video/`, uploaded participant media, credentials, or rendered
artifacts.

### Phase 0 — Baseline, safety, and executable fixtures

Goal: begin from a known-good baseline and make later media tests deterministic.

Steps:

1. Re-read repository state and inspect `git status`; preserve unrelated/user
   changes.
2. Run `make test` and record the baseline result in the implementation handoff.
3. Confirm `ffmpeg` and `ffprobe` versions and relevant codecs/filters without
   changing packages.
4. Add a test helper that generates tiny deterministic video and audio fixtures
   with allowlisted FFmpeg arguments in a temporary test directory.
5. Add capability detection for FFmpeg, ffprobe, drawtext/font availability,
   Termux commands, asciinema, and optional transcription tools. Detection must
   not activate the microphone, camera, sensors, or Android sharing.
6. Add a schema-version strategy and tests proving the current fixture project
   still loads.
7. Refactor the current `SAFE_COMMANDS` set into a minimal declared command
   registry containing schemas, context/authority metadata, revision behavior,
   and readback/effect descriptions for the commands that already exist.
8. Add a read-only application-contract endpoint and CLI/MCP discovery tool.
9. Add consistency tests proving every advertised command has an allowlisted
   handler and every externally invocable handler is advertised.
10. Clarify the README: the current version is a proof; name the first functional
   milestone and link to this plan.

Acceptance:

- Existing tests still pass.
- Capability detection is read-only and returns useful absent/present states.
- Deterministic media fixtures can be created and probed in tests.
- A paired Codex/Claude Code client can discover the real application contract
  without SAG Video holding a model-provider API key.
- The application contract does not itself grant mutation authority.
- No camera, microphone, sensor, share, or upload action occurs automatically.

### Phase 1 — Real managed-media intake

Goal: import one real MP4 and see it as an observed asset in the media library.

Steps:

1. Add `media_dir`, `proxy_dir`, upload-size limit, and allowed input types to
   settings.
2. Add the managed asset fields and backward-compatible model defaults.
3. Add storage methods for projects, assets, jobs, and schema migration as
   needed; keep database writes transactional.
4. Implement a managed-path resolver that rejects traversal and never derives a
   path directly from an uploaded filename.
5. Add multipart upload support with a strict byte limit. Stream to a temporary
   file inside the managed media root, calculate SHA-256, then atomically move
   the accepted source into place.
6. Probe the source using a fixed `ffprobe` argv. Reject unreadable files,
   unsupported stream sets, extreme dimensions/durations, or metadata outside
   configured limits.
7. Register only observed-valid assets in the usable media library. Retain
   bounded failure evidence and remove or quarantine rejected temporary data.
8. Generate a thumbnail and phone-friendly proxy as derived assets using fixed
   compiler logic.
9. Add upload/import API and CLI commands.
10. Wire the existing media `+` button to the Android/browser file picker.
11. Replace colored media thumbnails with real thumbnails and visible intake
    status.
12. Add receipt detail UI for the import hash and probe findings.

Security requirements:

- Sanitize display filenames but use generated storage identities.
- Never use `shell=True`.
- Never concatenate client data into FFmpeg filter expressions.
- Enforce request, file, duration, pixel-count, and stream-count limits.
- Serve media only through project-scoped opaque IDs.

Tests:

- Valid MP4 import and metadata.
- Valid audio-only import.
- Duplicate bytes receive clear deduplication behavior without identity
  confusion.
- Broken/truncated media returns observed failure.
- Filename traversal and unsupported type attempts fail closed.
- Upload retry with the same request ID is idempotent.
- Old generated fixture assets still load.

Acceptance:

- On Android, the user can select a real screen recording and see its actual
  thumbnail, duration, dimensions, and observed-valid receipt.
- The portrait phone layout has no forced desktop-width viewport: media intake,
  monitor, receipts, and primary actions remain readable and touch reachable;
  landscape retains the editor-oriented layout.
- No timeline/render functionality is implied merely by successful intake.

### Phase 2 — Real monitor and essential timeline editing

Status: completed through the interactive editing pass on July 22, 2026.

Goal: place imported media on the canonical timeline and preview actual content.

Steps:

1. Add project list/create/open flows and remove hardcoded `demo` assumptions
   from browser state while retaining the proof fixture as a sample.
2. Implement `timeline.insert_asset`, split, delete, move, source-range trim,
   clip transform, and audio-gain commands.
3. Validate track/media compatibility and source ranges on the server.
4. Make timeline item IDs stable across display refreshes and variant creation.
5. Add a real HTML video/audio preview backed by the proxy asset.
6. Implement play, pause, seek, playhead time, and selection synchronized with
   server state. Playback state itself may remain local and ephemeral.
7. Add click/drag timeline operations that dispatch semantic commands only on
   commit. During dragging, show an optimistic visual preview without mutating
   canonical state.
8. Handle stale revisions by refreshing and explaining the conflict; never
   silently replay a destructive edit.
9. Add split, delete, undo, zoom, and fit controls with mobile-accessible hit
   targets.
10. Expand the inspector for source in/out, transform, fit/crop, and gain.
11. Make the layout responsive: desktop/landscape editor, portrait drawers,
   accessible pairing dialog, and no controls hidden beyond the viewport.
12. Improve pairing UX: waiting state, copyable command, successful actor
   connection indicator, expiry, and explicit close/cancel behavior.
13. Generate GUI/CLI/MCP command descriptions from the same application registry
    where their transport permits it; avoid copying schemas by hand.
14. Include current selection, stable IDs, exact revision, active commands, actor
    scope, and pending approvals in the live context projection.
15. Demonstrate the no-API-key agent loop: Eyal types a text instruction to an
    already-running Codex or Claude Code terminal session, the agent discovers
    the selected timeline entity, invokes a semantic edit, and the browser
    reflects the new canonical revision.

Tests:

- Every semantic command succeeds, rejects invalid inputs, rejects stale
  revisions, and is idempotent by request ID.
- Split preserves exact source/timeline ranges with no gap or overlap unless
  requested.
- Undo creates a compensating revision.
- Project context and selection never grant extra commands.
- API tests cover creation, insertion, playback URLs, and pairing state.

Acceptance:

- A user can import a real clip, insert it, play it, seek it, split it, trim it,
  move it, delete/undo it, and see the same canonical state from CLI/MCP.
- Refreshing the browser does not lose edits.
- Codex can control the editor semantically from text through the paired terminal
  without an API key stored in SAG Video and without clicking screen coordinates.

### Persistence gate — Normalized SQLite before Phase 3

Status: completed July 22, 2026.

Goal: make render jobs, artifacts, observations, capture work, and cloud creative
runs durable without extending the original whole-project blob proof store.

Implemented:

1. Replaced project, event, receipt, and selection blobs with normalized,
   foreign-keyed tables and exact revision reconstruction.
2. Added revisioned asset snapshots so later metadata changes cannot rewrite
   historical projects.
3. Added ordered migrations with a one-step legacy importer, schema ledger,
   physical/application version separation, and startup foreign-key validation.
4. Migrated receipts into explicit transition, observation, and finding rows.
5. Changed undo to load the referenced historical revision rather than a stored
   `before_body` JSON document.
6. Added normalized job, attempt, artifact, capture, suggestion, approval,
   provider, model-run, interaction-thread, and generation-candidate tables.
7. Added storage-neutral project, receipt, job, and provider-run repository
   protocols and typed records.
8. Added a real `BEGIN IMMEDIATE` unit of work so nested repository writes cannot
   commit ahead of the surrounding command.
9. Preserved the existing live database through an integrity-checked backup and
   in-place migrations; unmaterialized generated slates are truthfully pending.
10. Defined table, query, transaction, lifecycle, backup, JSON, security,
    portability, and reconciliation requirements in `docs/persistence-spec.md`.

Verification:

- Legacy blob migration preserves head/history/selection/receipt/observation.
- Restart preserves current and exact historical asset state.
- Forced failure rolls back nested receipt writes.
- Job claiming, cancellation request, and interrupted-worker recovery persist.
- Provider/model runs survive restart without vendor-specific schema names.
- `PRAGMA integrity_check` and `foreign_key_check` pass.
- Full automated suite: 28 tests.

Phase 3 must use these job and artifact boundaries. It must not add a second job
database, reintroduce aggregate project blobs, or encode a specific cloud model
into columns or table names.

### Phase 3 — Real timeline compiler and asynchronous verified render

Status: functional vertical slice implemented July 22, 2026; hardening items
remain before the phase is frozen.

Goal: render actual timeline media and play the verified output.

Steps:

1. Extract a typed immutable render specification from one exact project
   revision and preset.
2. Validate the complete specification before dispatch: referenced assets,
   observed-valid inputs, source ranges, track ordering, duration, and output
   limits.
3. Replace the generated-color `_command` compiler with an argv compiler for:
   video input, source trim, timestamps, scale/pad/crop, clip concatenation,
   title overlays, audio trim/gain, audio mix, and explicit output mapping.
4. Escape title text through a safe strategy. Prefer generated subtitle/text
   files or tightly controlled filter inputs over embedding arbitrary strings in
   a filter expression.
5. Introduce a persistent bounded job runner. Start with one render worker on
   the phone to avoid thermal and memory contention.
6. Return accepted receipt/job immediately; expose polling and cancellation.
7. Write to a temporary artifact and atomically finalize it after FFmpeg exits.
8. Calculate artifact hash and move the receipt to awaiting observation.
9. Expand observation to validate video/audio streams, exact variant dimensions,
   duration tolerance, frame rate, decodable representative frames, and title
   safe area when applicable.
10. Register successful output as a derived artifact with a stable URL.
11. Add render progress, cancel, result player, file information, and failure
    findings to the GUI.
12. Keep the original deterministic unsafe-title proof as a focused observer
    test rather than the default user project.

Tests:

- Single real video clip render.
- Two clips with trims and a boundary.
- Video plus narration.
- Title with punctuation and non-Latin text.
- Invalid/missing source fails before FFmpeg dispatch.
- FFmpeg nonzero, timeout, cancellation, missing artifact, wrong dimensions,
  wrong duration, and observer exception all finalize truthfully.
- Frozen revision remains unchanged even if a later edit occurs during render.

Acceptance:

- An imported Android recording can be edited and rendered into a playable MP4.
- The output player uses the encoded artifact, not a DOM simulation.
- A successful render receipt contains artifact identity, hash, frozen revision,
  controller, observer deployment, and concrete findings.

### Phase 3.5 — Cloud creative candidates with Gemini Omni and Veo

Scheduling note, recalibrated July 22, 2026: retain this specification here, but
do not execute it immediately after Phase 3. Complete the Codex–SAG acceptance
milestone and the minimum narration/caption plus horizontal/vertical creator
slices first. Then implement the provider-neutral candidate foundation, Omni,
and Veo in that order.

Goal: add optional generative video as a bounded source of review candidates
without giving a model direct authority over the canonical timeline.

The source notes in `/storage/emulated/0/Download/gemini-video/omni.md` and
`veo.md` are vendor capability documentation, not executable agents. Implement
two declared SAG production roles on top of a provider-neutral adapter:

- `omni_creative_editor`: the default role for short text/image generation,
  uploaded-video transformation where regionally available, and conversational
  refinement through interaction lineage.
- `veo_shot_generator`: a specialist role for cinematic B-roll, reference-image
  direction, first/last-frame workflows, supported higher resolutions, and
  extension of eligible Veo-generated sources.

Implementation order and authority:

1. Do not begin this phase until the real managed-media, timeline, and verified
   render core in Phases 0–3 passes Gate A.
2. Read Gemini credentials only from server-side environment/secret storage.
   The editor and paired-terminal control remain usable without a provider key.
3. Expose provider/model availability and restrictions through the SAG
   application contract. Capability description never grants dispatch authority.
4. Let browser, CLI, MCP, Codex, or Claude prepare a `GenerationDraft` bound to
   one project revision, prompt, parameters, and opaque managed reference asset
   IDs.
5. Require a visible local-human approval before network dispatch or cost. If
   existing media will leave the device, disclose the exact assets and byte
   counts and require explicit egress consent.
6. Persist a `GenerationJob` before dispatch. Poll bounded provider operation
   state and recover truthfully after restart. Local cancellation stops polling
   and download when provider cancellation is unavailable; it must not claim the
   remote operation was cancelled.
7. Download provider output immediately into a quarantine generation directory;
   never treat a temporary provider URI as the durable asset identity.
8. Hash, probe, decode, and validate streams, duration, dimensions, and limits
   through the normal intake observers.
9. Store valid output as a `GenerationCandidate` with provider/model/version,
   source hashes, operation and interaction lineage, prompt provenance, observer
   findings, and creative-review state.
10. Show candidates beside their sources. Require explicit accept or reject.
    Acceptance imports one candidate as a managed derived asset. Timeline
    insertion is a separate revision-checked semantic command.
11. A successful generation receipt means only that a valid candidate artifact
    was received and observed. It does not prove prompt adherence, factual
    accuracy, artistic quality, or publishability.

Initial domain records:

- `AgentProfile`: stable role ID, provider, supported modes and constraints,
  approval requirements, and runtime availability.
- `GenerationDraft`: project/revision, role, prompt, managed references, aspect
  ratio, resolution, duration intent, outbound byte count, and approval state.
- `GenerationJob`: provider operation identity, lifecycle, retry state,
  timestamps, bounded errors, and local cancellation state.
- `GenerationCandidate`: quarantined artifact identity, hash/probe findings,
  provider provenance, source hashes, lineage, and accepted/rejected state.
- `InteractionThread`: Gemini Omni interaction lineage used for follow-up edits.

Initial HTTP surface:

- `GET /api/generation/capabilities`
- `POST /api/projects/{project_id}/generation-drafts`
- `POST /api/generation-drafts/{draft_id}/approve`
- `GET /api/generations/{generation_id}`
- `POST /api/generations/{generation_id}/cancel`
- `POST /api/generation-candidates/{candidate_id}/refinements`
- `POST /api/generation-candidates/{candidate_id}/accept`
- `POST /api/generation-candidates/{candidate_id}/reject`

Provider-specific rules:

- Prefer Omni for ordinary short generation and refinement. Preserve
  `previous_interaction_id` lineage, enforce the runtime-reported duration and
  resolution constraints, and reject unsupported multi-video inputs before
  dispatch.
- Use Veo only for requested specialist controls. Permit extension only when
  the source has valid Veo provenance and satisfies the provider's current
  constraints.
- Discover model names and parameter support from configuration/capability
  checks rather than encoding marketing labels into project semantics.
- Record provider watermark/provenance information as a finding where available;
  never use it as proof of creative correctness.

Tests use a deterministic fake provider and make no network requests:

- Missing credentials, unavailable model/region, safety rejection, timeout,
  malformed response, interrupted polling, and restart recovery.
- Idempotent approval/dispatch and enforced network/cost/media-egress gates.
- No filesystem paths, credentials, or provider secrets in public records.
- Immediate download and truthful expired-URI behavior.
- Invalid, truncated, wrong-format, wrong-dimension, and undecodable output.
- Omni refinement lineage and stale/missing interaction IDs.
- Veo extension provenance and parameter restrictions.
- Rejection has no project effect; acceptance creates exactly one managed asset;
  insertion remains a separate command.

Acceptance:

- With no Gemini key, the application reports both roles unavailable and the
  complete local editor still works.
- With local BYOK and explicit approval, Omni or Veo can produce an observed
  review candidate that survives refresh/restart.
- No candidate appears in the normal media library or timeline before explicit
  acceptance, and no model can approve its own egress, cost, acceptance, or
  insertion.

### Phase 4 — Narration, audio quality, and captions

Goal: create a complete narrated technical clip on the phone.

Steps:

1. Implement narration intake from an ordinary uploaded audio file first.
2. Implement a bounded Termux microphone adapter supporting explicit start and
   stop, duration limit, Opus/AAC allowlist, sample rate, bitrate, and channels.
3. Require a direct user action in the browser or local CLI before microphone
   activation. Display an active recording state and elapsed time.
4. Stop and finalize abandoned captures safely. Never leave the microphone
   running after timeout, server shutdown, or explicit cancellation when the
   adapter can prevent it.
5. Observe narration duration, stream readability, and non-silence before asset
   registration.
6. Add audio waveform/proxy data sufficient for timeline alignment without
   decoding the full source in the browser.
7. Add audio gain, mute, fade, and narration alignment controls.
8. Add a transcription adapter interface and implement local `whisper.cpp` only
   when its capability is present. Do not silently install or download models.
9. Persist transcription segments/words with source asset hash and model/tool
   provenance.
10. Convert transcript selections into editable caption items.
11. Compile captions with safe-area-aware styles and Unicode-capable fonts.
12. Add audio observers: stream present, non-silence, integrated loudness/peak
    targets, and excessive-silence findings. Start with informational findings;
    make a predicate blocking only after targets are explicitly chosen.

Tests:

- Narration upload and timeline mix.
- Capture capability absent/present behavior without activating the microphone
  in tests.
- Fake capture adapter lifecycle and timeouts.
- Silent narration is detected.
- Caption timing, Unicode text, line wrapping, and safe-area checks.
- Transcription provenance becomes stale when source bytes change.

Acceptance:

- The user can add narration and captions to a real screen recording and hear/
  see them in the verified output.
- Microphone recording is always visible, bounded, and user-initiated.

### Phase 5 — Horizontal/vertical variants and reviewable automation

Goal: create publishable 16:9 and 9:16 outputs from one episode.

Steps:

1. Add output-variant records referencing a shared editorial timeline plus
   variant-specific transform/title/caption overrides.
2. Implement landscape and vertical presets with correct safe areas.
3. Add fit, fill, crop, background blur/color, and focus-region transforms.
4. Allow the user or agent to declare the terminal/application region that must
   remain visible in vertical output.
5. Generate variant suggestions rather than mutating the base timeline.
6. Add silence detection and propose bounded cuts with pre/post-roll margins.
7. Add repeated-take markers as manual annotations first; only later infer them
   from transcript similarity.
8. Add scene-boundary analysis as optional evidence for cut suggestions.
9. Add a suggestion-review panel with accept, reject, preview, stale state, and
   explanation.
10. Render both presets through separate receipts/jobs bound to the same source
    revision.
11. Extend verification for caption/title safe areas, black frames, frozen
    sections, expected focus region, and thumbnail readability.

Tests:

- Variant overrides do not mutate the base editorial timeline.
- Suggestion acceptance creates ordinary revisioned commands.
- Rejected suggestions have no timeline effect.
- Stale suggestions cannot apply silently.
- Landscape and vertical artifacts independently satisfy their contracts.

Acceptance:

- One edited episode produces verified 1920×1080 and 1080×1920 artifacts.
- Automated cuts and reframes remain fully reviewable and reversible.

### Phase 6 — Terminal-native capture with asciinema

Goal: make Codex/Claude terminal demonstrations editable as semantic events
rather than phone-screen pixels.

Steps:

1. Add asciinema capability detection. Installation is an explicit user action,
   not an application side effect.
2. Define a terminal-capture manifest: geometry, theme, font, timing, markers,
   input-recording policy, and redaction state.
3. Implement a local CLI preparation/start flow that owns its TTY. Do not try to
   start an interactive terminal recorder as an unbounded remote web subprocess.
4. Make input recording opt-in because it can expose credentials and secrets.
5. Ingest the asciicast as a managed source with hash and format validation.
6. Add event-aware editing for pauses, speed changes, markers, and ranged
   redaction.
7. Add a conservative secret-pattern scanner and require review of flagged
   content. Never claim the scanner proves absence of secrets.
8. Implement a renderer adapter using an available deterministic renderer such
   as VHS/compatible worker, or a small controlled cast renderer if required.
9. Render the same cast for horizontal and vertical layouts with explicit
   terminal geometry and font size.
10. Bind render evidence back to expected markers or visible terminal regions.

Tests:

- Valid/invalid cast ingestion.
- Input-event policy defaults to off.
- Pause/speed/redaction operations preserve event order.
- Secret findings block unattended export but remain reviewable.
- Deterministic cast renders at both preset sizes.

Acceptance:

- A terminal session can become a polished clip without relying on a pixel-level
  phone screen recording.
- The user can remove waits and redact sensitive ranges before rendering.

### Phase 7 — Browser-native capture with Playwright

Goal: produce repeatable product demonstrations from declared browser actions.

Steps:

1. Add a worker-side Playwright capability adapter; do not require it for the
   core phone editor.
2. Store a bounded capture recipe: permitted origin, viewport, action sequence,
   expected checkpoints, and output settings.
3. Restrict navigation/origins and credentials to the capture job's explicit
   authority. Never expose a general browser-control proxy through SAG Video.
4. Capture video, screenshots, and semantic action timestamps.
5. Use action boundaries as suggested edit points.
6. Observe expected screenshots/content checkpoints and final media properties.
7. Add the result to the same managed asset/timeline pipeline.

Acceptance:

- A repeatable browser demo produces a managed video asset with semantic cut
  markers and observation findings.

### Phase 8 — Termux device workflow integration

Goal: make the phone production loop convenient without overstating Termux API
capabilities.

Steps:

1. Add a read-only device preflight for available Termux commands, battery,
   storage headroom, FFmpeg capability, and optional sensor names.
2. Add explicit wake-lock acquisition/release around user-approved long capture
   or render jobs. Always release on completion/failure where possible.
3. Use Termux notifications for capture/render status and actions such as open
   result or cancel where safely supported.
4. Use `termux-media-scan` after a verified artifact is copied into a user-
   selected export directory.
5. Use `termux-share` to open Android's share flow only after user approval.
6. Add camera-photo capture only for thumbnail/reference stills. Label it as
   still capture; do not imply Termux camera video recording.
7. Add optional, bounded sensor samples around a capture session for movement,
   orientation, and ambient-light warnings.
8. Sensor findings are advisory until a real workflow establishes a trustworthy
   predicate. Never sample all sensors continuously by default.
9. Add thermal/battery/resource warnings and recommend deferred/worker rendering
   when limits are exceeded; do not claim wake lock prevents Android process
   termination.

Acceptance:

- A verified result can be placed in the Android gallery and opened in the share
  sheet through an explicit human action.
- No camera, sensor, microphone, or share operation begins on application load,
  capability scan, or agent request without the required user gate.

### Phase 9 — Android SAG Capture companion

Goal: capture clean app-only screen video and camera video that Termux API does
not provide.

Do not begin until the import-based creator loop is used successfully and the
missing capture friction is confirmed.

Steps:

1. Write a separate Android companion technical design before code.
2. Use MediaProjection with the required foreground service and visible consent
   for each session.
3. Prefer app-only sharing/capture on supported Android versions so status bar,
   notifications, and unrelated applications remain excluded.
4. Add internal playback audio only where source applications allow capture.
5. Use CameraX for bounded FHD/UHD camera recording and explicit audio consent.
6. Pair the companion to a SAG Video workspace with scoped, short-lived tokens.
7. Hand off artifacts by content URI/stream into managed intake; never grant the
   web service broad storage access.
8. Show capture source, recording indicator, elapsed time, stop control, and
   expected destination.
9. Observe duration, orientation, streams, unexpected black frames, audio, and
   optional expected app identity before declaring capture success.
10. Threat-model malicious intents, token leakage, background recording,
    notification exposure, and abandoned foreground services.

Acceptance:

- A user can explicitly approve and capture one application or camera take and
  receive it as an observed SAG Video asset.
- An agent cannot grant Android capture consent or start hidden recording.

### Phase 10 — Human-gated publishing

Goal: reduce posting friction without confusing upload dispatch with a published
video.

Steps:

1. Keep Android gallery/share as the default TikTok path.
2. Add an episode release checklist: output predicates, secret review, caption
   review, thumbnail, title/description, disclosure, and final human approval.
3. Implement resumable YouTube uploads only to a private draft initially.
4. Store platform credentials outside project JSON and receipts; record only
   scoped provider/account identity needed for auditing.
5. Require a visible approval step immediately before external upload.
6. Observe the provider response and returned video ID/status. Treat upload
   initiation as nonterminal.
7. Do not automate TikTok Direct Post until the product has a compliant broad-
   user use case and completes the required audit. Do not build around private-
   only unaudited behavior as though it were production publishing.
8. Never burn SAG Video or promotional watermarks into content destined for a
   platform that prohibits them through its posting integration.

Acceptance:

- YouTube can receive a human-approved private draft with a causal receipt.
- TikTok remains a human-controlled share action until compliance requirements
  are satisfied.

### Phase 11 — Service hardening and commercialization gate

Goal: decide whether the proven personal workflow should become a hosted
service.

Do not assume this phase is justified by a successful personal prototype.
Require actual usage evidence: repeated episodes, measured hands-on time, output
quality, reliability, and external willingness to use or pay.

If justified:

1. Replace local SQLite/job execution with interfaces suitable for PostgreSQL,
   object storage, and a bounded render queue.
2. Add tenant/workspace isolation, quotas, retention, deletion, audit events,
   malware/media validation, and encrypted storage.
3. Separate public control, private workers, and independent observers.
4. Add authenticated uploads and downloads with short-lived scoped URLs.
5. Add resource/concurrency admission and cost accounting before accepting work.
6. Add backup/recovery and deletion verification.
7. Add billing only after the unit economics of transcription, storage, render,
   observation, and support are measured.
8. Complete privacy, terms, copyright, platform-policy, and security review.

## 11. First functional release definition

Call the product functional—not complete—when all of the following work in one
clean run:

1. Create or open a non-fixture project.
2. Import a genuine MP4 through Android/browser file selection.
3. Observe and register the asset with hash and probed streams.
4. Insert it on the timeline.
5. Play and seek the actual proxy.
6. Split, trim, move, delete, and undo through semantic commands.
7. Add narration from a real audio asset.
8. Add a title and editable captions.
9. Render at least one real output asynchronously.
10. Play the encoded result in the application.
11. Inspect a receipt with concrete stream/duration/frame/audio/title findings.
12. Export/share the verified artifact through an explicit user action.
13. Perform the same core timeline and render operations through CLI/MCP.
14. Restart the service and retain the project, assets, timeline, jobs, and
    receipts.

The stronger creator-loop milestone additionally requires both horizontal and
vertical output from the same episode and a measured hands-on production time.
The initial target is no more than approximately 15 minutes of hands-on work
for a 30–60 second Codex tip after the source take exists. Treat this as a
product target to measure, not as a demonstrated claim.

## 12. Verification strategy

### 12.1 Test layers

- Pure unit tests for time math, project validation, path safety, command
  compilation, caption layout, and observation predicates.
- Store tests for migrations, transactions, idempotency, and restart recovery.
- API tests for auth, project scope, revision conflicts, uploads, jobs, pairing,
  and artifacts.
- FFmpeg integration tests using tiny generated media.
- Observer mutation tests where the output is intentionally wrong, truncated,
  silent, clipped, or replaced after handoff.
- Browser interaction tests after the editor controls stabilize; Playwright is
  useful here but should not block early backend work.
- Manual Android acceptance checks for file picker, rotation, landscape editor,
  portrait drawers, microphone gate, gallery, share sheet, and backgrounding.

### 12.2 Render observer progression

Implement predicates in this order:

1. File exists and handoff hash matches.
2. ffprobe reads expected video/audio streams.
3. Dimensions, frame rate, codecs, and duration satisfy the frozen contract.
4. Representative frames decode.
5. Titles/captions are visible inside declared safe regions.
6. Audio is present when required and not effectively silent.
7. Loudness/peak findings.
8. Black/frozen interval findings.
9. Expected terminal/browser focus region.
10. Conservative sensitive-text findings with explicit uncertainty.

Each finding includes a stable code, pass/fail or informational severity,
summary, evidence, tool/version, and observation timestamp.

### 12.3 Definition of done for every phase

- Feature is reachable through the intended surface, not only a private helper.
- Authority and validation boundaries are explicit.
- Failure, retry, timeout, cancellation, stale revision, and restart behavior are
  tested where applicable.
- Receipt language matches what was actually observed.
- Documentation and examples match the implementation.
- `make test` passes.
- No real captured/uploaded media, secrets, tokens, databases, or artifacts are
  committed.

## 13. Mobile and usability requirements

The screenshots establish phone use as a primary environment, not a later
responsive-design concern.

- Landscape: monitor and timeline remain central; media and inspector can become
  collapsible drawers.
- Portrait: use one primary pane with explicit Media, Monitor, Timeline, and
  Inspector tabs/drawers rather than a squeezed desktop canvas.
- Keep destructive actions labeled and separated.
- Make playback, split, undo, record, render, and review reachable with touch-
  sized controls.
- Preserve visible selected item, revision, render/capture status, and current
  output preset.
- Do not fake live playback with CSS elements once real media exists.
- Pairing must show whether a terminal actually attached and which actor name it
  received.
- Long tasks survive browser refresh and can be inspected after reconnecting.

## 14. Security and privacy checklist

- Managed media roots are explicit and never broad paths such as the workspace
  root or Android shared-storage root.
- Browser/agent APIs never read arbitrary server paths.
- Subprocesses use fixed executables and argv arrays, never a shell.
- FFmpeg graphs are compiled from validated typed values.
- Uploads have byte, duration, pixel, stream, and concurrency limits.
- Artifact endpoints are project/workspace scoped.
- Pairing codes remain single-use and short-lived; tokens are scoped, expiring,
  and revocable.
- Raw terminal input capture is off by default.
- Credentials and sensitive findings are not copied into normal logs.
- Camera, microphone, sensor, screen capture, gallery, share, and publish actions
  have explicit human gates.
- Android companion permissions are minimal and purpose-specific.
- Source and derived-media deletion semantics are documented before hosting
  external user data.
- Participant or customer media never enters the canonical public SAG evidence
  repository without explicit permission and sanitization.

## 15. Performance and reliability constraints

- Generate proxies for editing; do not decode 4K sources continuously in the
  browser.
- Begin with one concurrent phone render and one capture session.
- Bound FFmpeg and observer time, CPU/memory at the deployment boundary, output
  size, and intermediate-file retention.
- Use atomic artifact finalization so incomplete files are never served as final
  results.
- Persist jobs before dispatch and recover interrupted jobs truthfully on
  startup.
- Hash streams while copying where practical instead of rereading large files.
- Prefer worker rendering for long/high-resolution jobs once the adapter exists.
- Wake locks reduce sleep interruption but do not prove Android will preserve a
  CPU-heavy process.

## 16. Explicitly deferred scope

Do not implement these before the first creator loop proves their necessity:

- General-purpose OpenCut feature parity.
- Arbitrary effects or plugin execution.
- Multicam editing.
- Collaborative simultaneous editing or generalized CRDT concurrency.
- PostgreSQL equivalence claims.
- Distributed leases.
- Reconstruction or certification claims.
- RAG/NLKE features.
- Generative video or image services.
- Automatic public posting.
- Marketplace, billing, or multi-tenant SaaS.
- Continuous sensor recording.
- Silent/background screen, camera, or microphone capture.

## 17. Decision gates

### Gate A — Real editor core

Proceed beyond Phase 3 only if a real imported clip can be edited, rendered,
played, and truthfully verified on the target phone.

### Gate B — Creator-loop usefulness

Proceed to specialized capture/publishing only if at least three actual episodes
are completed and the workflow shows meaningful reduction in manual work while
maintaining publishable quality.

Record for every episode:

- Source/capture type.
- Total elapsed and hands-on time.
- Manual interventions.
- Render failures and observer catches.
- Output variants produced.
- Whether the result was actually published.
- What still required another editor.

### Gate C — Android companion

Build the companion only if manual imports or existing Android screen recording
are a repeated bottleneck that MediaProjection/CameraX would materially solve.

### Gate D — Hosted service

Begin service hardening only with credible external workflow demand, a bounded
target user, and evidence that the verified terminal/GUI pipeline—not merely
ordinary editing—is valuable.

## 18. Immediate implementation start after compaction

When implementation begins, do the following in order:

1. Read this entire document and the current repository instructions/docs.
2. Inspect `git status` and preserve all existing user work.
3. Run the baseline test suite.
4. Start Phase 0 only.
5. Add deterministic media fixtures and read-only capability detection.
6. Verify Phase 0 and report the exact result.
7. Continue directly into Phase 1 unless a real safety/authority blocker appears.
8. Stop at the Phase 1 acceptance gate with a working Android-browser media
   import, observed asset, thumbnail/proxy, tests, and documentation.

Do not begin with sensors, the Android companion, transcription, publishing, or
visual polish. The critical path is:

```text
real file → observed managed asset → canonical timeline → actual render
```

## 19. Proven Termux adapter notes from the earlier mobile-actions project

The following operational notes were extracted on July 22, 2026 from:

- `/storage/emulated/0/Download/claude-projects/qwen2.5-7B-instruct/docs/MOBILE-ACTIONS-V2-HANDOFF.md`
- `/storage/emulated/0/Download/claude-projects/qwen2.5-7B-instruct/docs/obscure-web-research.md`

That project reported 201 passing tests and 26 on-device actions, including a
microphone/ASR/TTS loop, camera document capture, bounded sensor sampling, and
notifications. Treat those results as useful prior implementation evidence, not
as proof that every command still works after Termux, Termux:API, Android, or
device changes. SAG Video must capability-check and re-observe every adapter.

The installed Termux wrapper scripts were also inspected read-only when these
notes were added. No microphone, camera, sensor, notification, share, or other
device action was activated during extraction.

### 19.1 Implementation pattern to retain

The useful prior pattern is:

```text
typed requested action
→ allowlisted argv adapter
→ bounded timeout and explicit permission/user gate
→ actual output artifact or structured JSON
→ probe/validate/normalize
→ cloud-model request when useful
→ semantic suggestion or result
→ observed effect receipt
```

Retain these lessons:

- Use list-form subprocess arguments with no `shell=True`.
- Add timeouts even to commands expected to return immediately. The earlier
  project found that missing Termux:API permissions can produce empty results or
  indefinite hangs instead of clear errors.
- Validate returned JSON and media rather than trusting process exit alone.
- Run cleanup/stop commands in `finally` paths where applicable.
- Log bounded exception detail rather than swallowing broad exceptions.
- Prefer persisted job state or polling over a browser-only SSE stream. Android
  may throttle a background browser tab while the server continues working.
- Use `am`, not the obsolete `termux-am`, if an Android intent is eventually
  required.
- Never copy the earlier screen-agent's unrestricted tap/swipe/text primitives
  into SAG Video's agent authority. They are outside the video editor contract.

### 19.2 Cloud-model adaptation

The earlier project loaded and swapped local specialist models. SAG Video should
use cloud-model adapters instead, while keeping all device execution local and
bounded.

Cloud models may be used for:

- Speech transcription and word timing.
- Caption cleanup and line-break suggestions.
- Edit-plan suggestions from transcript/timeline metadata.
- Detection suggestions from user-approved thumbnails or sampled frames.
- Titles, descriptions, hooks, chapters, and platform variants.
- Later, visual review of a deliberately selected low-resolution proxy.

Requirements:

- Use a provider-neutral interface so the configured cloud model can change.
- Keep API credentials in environment/secret storage, never project JSON,
  receipts, browser storage, or CLI output.
- Record provider, model/version, request purpose, source artifact hash, and
  timing in provenance without recording credentials.
- Require explicit consent before media, audio, frames, transcripts, or other
  potentially private content leaves the device.
- Prefer transcript/timeline metadata over full video upload when sufficient.
- Bound input size, sampled frames, cost, timeout, and retry count.
- A cloud response creates a suggestion or intermediate artifact. It does not
  prove that the timeline changed or the final video contains the intended
  result.
- Keep the original media and deterministic FFmpeg/observer pipeline usable when
  a cloud provider is unavailable.
- Do not reproduce the earlier local model-swap machinery in SAG Video.

### 19.3 Microphone recording adapter

Installed wrapper syntax:

```text
termux-microphone-record -f FILE -l SECONDS -e ENCODER -b KBPS -r HZ -c CHANNELS
termux-microphone-record -i
termux-microphone-record -q
```

Supported installed encoders are `aac`, `amr_wb`, `amr_nb`, and `opus`.
A conservative first narration request is equivalent to this argv:

```text
termux-microphone-record -f CAPTURE.m4a -l 60 -e aac -b 128 -r 48000 -c 1
```

Implementation requirements:

1. Generate `CAPTURE` inside the managed capture directory; never accept a raw
   browser/agent path.
2. Require an explicit local user action before starting.
3. Persist the capture session before invocation.
4. Bound duration; do not use unlimited `-l 0` in the initial adapter.
5. Use `-i` for bounded status checks and `-q` for stop/cancellation.
6. Always probe the completed bytes. The earlier project found that requesting
   PCM did not guarantee PCM: the device produced an ISO Media/MP4/M4A file
   regardless of the requested extension/encoder flag.
7. Treat filename extensions and requested encoder as intent, not observation.
8. Normalize only after probing. For cloud speech services requiring 16 kHz mono
   WAV, the controlled conversion is equivalent to:

   ```text
   ffmpeg -nostdin -y -i CAPTURE.m4a -vn -ar 16000 -ac 1 ASR.wav
   ```

   For editing/mixing, retain the observed source and create a separate derived
   48 kHz proxy when required by the renderer.
9. Detect unexpectedly small/silent captures before cloud upload. The earlier
   project used a 10 KB heuristic and ASR repetition checks; SAG Video should
   replace file size alone with duration plus decoded audio/silence evidence.
10. Register the recording as an asset only after hash, stream, duration, and
    non-silence observation.

Never invoke continuous ambient listening or a wake-word loop as part of the
initial video product.

### 19.4 Camera still adapter

Installed wrapper syntax:

```text
termux-camera-info
termux-camera-photo -c CAMERA_ID OUTPUT.jpg
```

The camera command creates JPEG stills only. SAG Video may use it for a
thumbnail, slate, document/reference shot, or a cloud-vision-assisted suggestion.
It is not the camera-video pipeline.

Implementation requirements:

- Call `termux-camera-info` only during an explicit capability/preflight action.
- Require a local user action and Android camera permission before capture.
- Create `OUTPUT.jpg` inside the managed capture directory.
- Probe/decode the JPEG, hash it, validate dimensions, and generate a thumbnail
  before asset registration.
- Show the still for review before sending it to any cloud vision model.
- Keep vision output as extracted/suggested metadata until the user applies it.
- Use CameraX in the future Android companion for actual camera video.

### 19.5 Bounded sensor adapter

Installed wrapper syntax:

```text
termux-sensor -l
termux-sensor -s SENSOR_NAMES -d DELAY_MS -n SAMPLE_COUNT
termux-sensor -c
```

An eventual SAG Video preflight may use an argv equivalent to:

```text
termux-sensor -s accelerometer,gyroscope,light -d 250 -n 8
```

The actual names must come from `termux-sensor -l`; the wrapper accepts partial
names, which can match more than intended, so the adapter must resolve and show
the selected sensors before sampling.

Implementation requirements:

- Never use `-a` by default; the wrapper itself warns of battery impact.
- Always specify a finite `-n` and a bounded subprocess timeout.
- Call cleanup after sampling or interruption.
- Store only summarized capture-quality findings unless raw samples are needed
  and approved.
- Initial findings are advisory: movement, rotation change, or large ambient-
  light change. They do not independently prove video quality.
- Do not send raw sensor streams to a cloud model for the first product loop.

### 19.6 Battery, wake lock, notification, gallery, and sharing

Installed commands relevant to the production loop:

```text
termux-battery-status
termux-wake-lock
termux-wake-unlock
termux-notification --id ID --ongoing --title TITLE --content CONTENT
termux-notification-remove ID
termux-media-scan -v OUTPUT.mp4
termux-share -a send -c video/mp4 -t TITLE OUTPUT.mp4
```

Adapter rules:

- Parse and validate battery JSON; use it for a warning/admission decision, not
  an assurance that a render will survive Android process management.
- Pair every acquired wake lock with release on normal completion, failure,
  cancellation, timeout, and best-effort shutdown recovery.
- Use a stable notification ID so progress updates replace the previous
  notification. Avoid arbitrary notification action strings because the Termux
  wrapper executes them through a shell. If actions are later needed, point only
  to a fixed audited script with fixed arguments.
- Do not treat `termux-media-scan` dispatch as proof that a file is visible in
  every gallery. Report the bounded media-scan response and keep the original
  verified artifact identity.
- `termux-share` opens Android's user-facing handoff. Do not use its default-
  receiver option in the initial product; preserve the chooser and human gate.
- Sharing is `awaiting_approval`/handoff evidence, not proof that TikTok,
  YouTube, or another application published the video.

### 19.7 Permission and failure preflight

Termux:API installation alone is insufficient. Each device capability can
require an Android permission or special access grant. Before a capture/export
flow:

1. Show which capability will be used and why.
2. Run a bounded capability check that does not itself capture private data
   where possible.
3. Distinguish command missing, Termux:API app/signature mismatch, permission
   missing, timeout/hang, empty/malformed response, user denial, and hardware
   absence.
4. Offer the relevant Android settings direction without trying to grant the
   permission programmatically.
5. Recheck only after the user returns.

The prior project specifically found notification-list could hang when Android
Notification Access was not granted. SAG Video does not currently need to read
notifications, so do not add that permission or capability merely for progress
notifications.

### 19.8 Commands deliberately excluded from SAG Video authority

The source handoff contains many working general-phone actions. Do not expose
the following through SAG Video merely because they are technically available:

- SMS, contacts, calls, call logs, location, Wi-Fi/cell data, fingerprint,
  clipboard, NFC, infrared, notification reading, or broad content queries.
- `uiautomator` plus raw `input tap/swipe/text/keyevent` app automation.
- Arbitrary `am start`, `settings`, `svc`, MQTT, or notification shell actions.
- Continuous microphone or sensor loops.

They do not belong to the video-production authority boundary and would expand
privacy, security, and review obligations without helping the critical path.

### 19.9 Reusable capability-intersection method

The obscure-research document contributes a useful future ideation method:

1. Inventory concrete capabilities without designing features yet.
2. Extract direct one-capability features.
3. Explore cross-category combinations and three-step chains.
4. Ask what changes if a bounded single-shot operation becomes a continuous
   loop, while accounting for privacy, battery, and authority costs.
5. Filter by verified hardware, permissions, dependencies, latency, impact, and
   effort.
6. Re-run the inventory when phone hardware, Android, Termux, or cloud-model
   capabilities change.

For SAG Video, promising bounded intersections include:

- Terminal events + cloud transcript reasoning + semantic timeline suggestions.
- Screen/camera asset + cloud visual review + verified FFmpeg output.
- Microphone narration + cloud transcription + editable word-timed captions.
- Battery/thermal preflight + job admission + worker offload recommendation.
- Bounded motion/light samples + capture-quality warning + retake prompt.
- Verified artifact + Android share sheet + human publishing approval.

Avoid turning the “continuous loop” prompt into default surveillance. Continuous
capture requires a separate product case, explicit consent, persistent visible
state, and a much stronger privacy design.

## 20. Technical references from the July 22 research

- Termux camera still command:
  <https://github.com/termux/termux-api-package/blob/master/scripts/termux-camera-photo.in>
- Termux microphone recording:
  <https://github.com/termux/termux-api-package/blob/master/scripts/termux-microphone-record.in>
- Termux sensors:
  <https://github.com/termux/termux-api-package/blob/master/scripts/termux-sensor.in>
- Termux application limitations and ecosystem:
  <https://github.com/termux/termux-app>
- Android MediaProjection:
  <https://developer.android.com/media/grow/media-projection>
- Android application screen sharing:
  <https://developer.android.com/about/versions/14/features/app-screen-sharing>
- Android CameraX:
  <https://developer.android.com/media/camera/camerax>
- asciinema:
  <https://github.com/asciinema/asciinema>
- VHS terminal renderer:
  <https://github.com/charmbracelet/vhs>
- Playwright video capture:
  <https://playwright.dev/docs/videos>
- whisper.cpp:
  <https://github.com/ggerganov/whisper.cpp>
- FFmpeg filters:
  <https://ffmpeg.org/ffmpeg-filters.html>
- PySceneDetect:
  <https://github.com/Breakthrough/PySceneDetect>
- YouTube resumable upload:
  <https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol>
- TikTok Content Posting guidelines:
  <https://developers.tiktok.com/doc/content-sharing-guidelines/>
