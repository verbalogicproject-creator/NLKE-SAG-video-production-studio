# Implementation status

Updated: July 23, 2026

## GCP beta control-plane foundation

The repository now includes the production-facing control-plane foundation:

- GCS resumable upload sessions with server-owned object keys, generation,
  size, MIME, workspace, and quota verification.
- Invite-only Google account admission, role-bound workspaces, hashed scoped
  API keys, and authenticated Streamable HTTP MCP tools.
- Canonical jobs, transactional outbox rows, duplicate-safe dispatcher claims,
  Cloud Tasks OIDC dispatch, expired-lease reconciliation, and daily/concurrent
  quotas.
- Human-bound, single-use private YouTube approvals, KMS-encrypted OAuth tokens,
  a resumable publisher with ambiguous-result reconciliation, and audit events.
- Terraform for regional GCS, private Cloud SQL, Cloud Run services/jobs,
  service accounts, KMS, Secret Manager, Artifact Registry, Cloud Tasks,
  Scheduler, Monitoring, and optional billing budgets.
- A focused Chamber edit surface for trims, hook titles, caption style and
  position, crop framing, gain, mute, revision readback, render, and evidence.

This is not yet an externally admissible beta. The Python SAG runtime still
uses its SQLite/filesystem adapter, so the Cloud Run job definitions must not be
enabled until the PostgreSQL SAG repository, GCS media/artifact adapter,
one-shot canonical job runner, importer, and database migration drill are
implemented and pass the cloud acceptance suite.

## Baseline

- The original proof slice passed 9 tests with one upstream Starlette/httpx
  deprecation warning.
- Runtime capability detection found FFmpeg and ffprobe 8.1.2 and the required
  `drawtext`, `showwavespic`, `loudnorm`, and `silencedetect` filters.
- Detection did not activate microphone, camera, sensors, media scan, or share.

## Completed slice

Phases 0–2 and the normalized persistence gate are implemented:

- Versioned project defaults and legacy fixture loading.
- One declared command registry feeding dispatch and application discovery.
- HTTP, CLI, and MCP contract/context/active-command discovery.
- Read-only executable/filter capability reporting.
- Bounded managed video/audio uploads using caller-provided bytes, opaque
  identities, SHA-256, ffprobe validation, generated proxy/thumbnail, causal
  receipts, idempotency, and content deduplication.
- Android/browser file-picker integration and a responsive phone layout.
- Project list/create/open flows and live context projection.
- Revision-checked insert, move, split, trim, delete, visual transform,
  audio-gain, title, and undo commands across GUI, CLI, and MCP.
- Real proxy playback, range seeking, playhead, dynamic ruler/zoom, timeline
  selection/dragging, touch controls, and visible terminal connection state.
- Continuous sequence playback switches managed proxies at canonical clip
  boundaries and advances through timeline gaps. Each lane projects the shared
  playhead.
- Selected video supports direct monitor drag, uniform resize, and rotation;
  the inspector exposes start, duration, source-in, fit, x/y, scale, rotation,
  opacity, gain, and mute.
- Timeline clips expose touch-friendly left/right edge handles. Left trims
  atomically update timeline start, source-in, duration, and source-out in one
  revision; move and trim endpoints snap to nearby semantic boundaries.
- CLI and MCP expose the same complete trim and clip-transform commands used by
  the browser.
- Migration-driven normalized SQLite project revisions, asset versions, events,
  receipt transitions/observations, jobs, artifacts, and provider-neutral model
  runs; no whole-project or before/after event blobs remain.
- Storage-neutral repository protocols and an atomic `BEGIN IMMEDIATE` unit of
  work for project/event/receipt changes.
- Restrained matte-charcoal editor chrome with a single warm interaction accent,
  muted semantic status colors, consistent radii, and no neon gradients or
  glow decoration. On phones, media is a horizontal reel and section navigation
  is fixed within thumb reach while monitor, timeline, inspector, and receipts
  retain their working semantic surfaces.

## Talking-head shorts milestone

- Workspace-scoped source/derived projects and content-addressed media sharing.
- Persistent `shorts.generate` analysis jobs with stage progress, cancellation,
  immutable source inputs, and cached transcript/media-feature artifacts.
- Local multilingual whisper.cpp and remote Whisper-compatible transcription,
  plus optional OpenAI-compatible structured ranking and deterministic fallback.
- Boundary-aligned 15–90 second candidate generation with a documented Clip
  Score breakdown and exact source word evidence.
- Optional MediaPipe dominant-face smoothing and stable two-person split plans;
  centered low-confidence framing remains available without MediaPipe.
- Independent 9:16 project acceptance, English/Hebrew active-word captions,
  caption presets/controls, manual crop keyframes, proxy preview, and FFmpeg
  render-spec `sag-render-0.2` support.
- Browser, HTTP, CLI, and MCP generation, review, acceptance, caption, crop,
  render, cancellation, and receipt surfaces.

## Verification

- Automated suite: 38 tests, including the shorts and Codex-link authority additions.
- Legacy blob migration, restart reconstruction, rollback, job recovery,
  provider neutrality, SQLite integrity, and foreign keys are covered.
- Live local server: contract discovery returned HTTP 200; CLI MP4 import
  returned an observed-valid H.264/AAC asset with proxy and thumbnail IDs.
- Remaining manual checks are real in-browser proxy playback/seeking, insert,
  split/drag/delete/undo, and landscape behavior on the target phone.

## Android acceptance result

The July 22 phone run imported a genuine clip, displayed its real thumbnail,
and showed the `asset.import` receipt as `observed_success` with its hash at
revision 3. Portrait Media, Monitor, Timeline, Inspector, and Receipts remained
readable. The run exposed and corrected a clipped third-media-card region and a
misleading `observed_valid` default on legacy generated slates. Landscape and
real proxy playback remain part of the next manual/editor check.

## Phase 3 functional slice

The first real-media Phase 3 vertical slice is implemented:

- Typed immutable render specifications bound to an exact project revision and
  observed source hashes.
- Pre-dispatch rejection for missing, changed, unobserved, incompatible, or
  out-of-range media.
- Allowlisted FFmpeg graphs for multiple video clips, trims, transforms, UTF-8
  title text files, embedded audio, narration tracks, gain, and mute.
- One persistent phone worker with atomic claim, cancellation request, crash
  interruption, timeout/nonzero failure, and bounded error evidence.
- Atomic artifact finalization, hashing, normalized registration, and safe
  content serving.
- Observation for hash, dimensions, frame rate, audio presence, duration,
  representative decoding, and title safe area.
- HTTP, GUI, CLI, and MCP polling/cancellation surfaces plus verified playback.

Automated verification includes a real H.264/AAC render, a two-clip trimmed
render with punctuation and Hebrew title text, and a mixed Hebrew/English
active-caption render with a time-varying crop path.

Remaining hardening includes wrong-dimension fixtures, richer FFmpeg progress,
output caption/loudness predicates, a curated human clip-quality benchmark,
and longer target-phone thermal testing.

The persistence contract is frozen for Phase 3 in `docs/persistence-spec.md`.
The pre-normalization live database backup is retained alongside the development
database as `.sag-video/sag-video.db.pre-normalized-20260722`.

## Codex–SAG link

Implementation preparation is complete; the first user-visible Codex acceptance
run remains pending because a new Codex session must load the project-local MCP
configuration.

- `.codex/config.toml` declares the local stdio MCP server without embedding a
  secret.
- Pairing can store an eight-hour token in ignored local state with mode `0600`;
  the MCP server rereads it on every call.
- Pairing identity and project scope are enforced on loopback and
  invite-protected deployments.
- An authenticated actor overrides caller-supplied attribution.
- Paired tokens cannot list, inspect, mutate, render, or retrieve resources from
  another project.
- MCP exposes project listing, shared semantic selection, shorts discovery and
  acceptance, caption/crop editing, rendering, and evidence inspection.
- The browser already polls canonical revisions and reflects agent commits
  within approximately 2.5 seconds.
- `scripts/codex_link_preflight.py` verifies the read-only contract/context
  prerequisites. The complete acceptance prompt and gates are documented in
  `docs/codex-sag-link.md`.

Recalibrated execution order:

1. Run the live Codex semantic edit/render/receipt acceptance.
2. Install a multilingual whisper.cpp model and run the first real English and
   Hebrew talking-head discovery benchmarks.
3. Tune clip scoring and face framing against the curated benchmark.
4. Add output caption/loudness observation and phone thermal measurements.
5. Evaluate B-roll and publishing only after three measured creator-loop runs.
