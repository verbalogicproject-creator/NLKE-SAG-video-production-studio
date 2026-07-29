# Implementation status

Updated: July 29, 2026

Implementation has advanced from Dogfood Pause 0 into the UI/UX release-candidate
hardening pass. The approved pause criteria and ordered gates remain recorded in
[`workflows/dogfood-pause-gates.md`](workflows/dogfood-pause-gates.md). The current
release position is **RC0 verified Studio delivery complete; stable exit not yet
reached**. Mobile/browser acceptance, accessibility, and production deployment
evidence remain open gates.

## Verified Studio delivery checkpoint

- Studio now targets the sequence selected by the route across project refresh,
  runtime events, spatial frames, managed media, screenshot review, render, and
  delivery. It no longer silently falls back to the control project's first
  engine project after initial page load.
- Project and sequence names are editable in Studio. The engine project name is
  changed through the declared, revision-checked `project.rename` command, then
  the control-plane project and exact Studio sequence are synchronized in one
  transaction.
- The global runtime strip exposes connecting, connected, reconnecting, and
  offline states plus the latest render receipt transition. Active renders poll
  at two seconds while the normal connected reconciliation remains fifteen
  seconds.
- Verified video and JSON receipt downloads are available in both Deliver and
  Governance. The same-origin download routes require an `observed_success`
  `render.verified` receipt, matching artifact ID and SHA-256, passed QC, exact
  sequence ownership, and authenticated workspace access. Failed-QC downloads
  return HTTP 409.
- The local dogfood Studio is named `SAG Repository Proof` with sequence
  `SAG Repository Short 9x16`. It exposes the accepted 30-second 1080x1920
  hybrid artifact and receipt at project revision 21. The cut retains the
  cinematic motion language of the earlier concept while authentic SAG Studio
  screenshots occupy the evidence-bearing UI regions. A download through the
  Studio route reproduced SHA-256
  `3d3cffbd88242aa779b06de6296672e50a4f6cbd0fbb80fd33277c702be30141`.
- The accepted audio contains a 29.9-second narration edit plus the original
  music bed. Observer v0.2 now blocks a designated Narration track when decoded
  spectral entropy is below the non-tonal activity threshold, preventing an
  amplified low-level tone from passing merely because its stream and LUFS are
  valid. The accepted artifact measured 0.15239 against the 0.10 minimum,
  -14.9 LUFS integrated loudness, and -1.4 dBFS true peak. Re-observing the
  rejected hum artifact through the same contract produced 0.06080 and failed
  the new blocking check.
- Verification on July 27 passed the full SAG engine suite with one expected
  skip, all workspace TypeScript checks, and the optimized Next.js production
  build. The new Playwright cases are committed and typechecked, but browser
  execution remains a Linux CI/staging gate because Playwright does not ship a
  supported Android/Termux browser runtime.

## Unified Studio and SAG Spatial Runtime

The foundational spatial runtime slice is implemented and verified locally:

- The additive `sag-spatial-frame/1.0` perceptual binding plane is implemented.
  Studio self-declares revision-bound, metadata-only viewport frames using an
  adaptive minimum-44-pixel grid, normalized geometry, stable semantic IDs,
  eligible actions, source, confidence, and redaction state. Current-frame,
  frame-readback, region-resolution, and effect-observation endpoints are
  exposed through FastAPI, same-origin Next routes, and read-only MCP tools.
- Frame-bound directives now preserve before/after frame IDs, binding identity,
  the semantic action route, changed entities, changed grid cells, and verified
  effect status. Unknown entities, stale projections, mismatched bindings,
  unsafe coordinate routes, raw screenshot fields, unredacted Gemini bindings,
  and oversized declarations fail closed. Gemini observation and coordinate
  fallback remain disabled by default.
- Storyboard scenes can carry optional spatial layout contracts for authentic
  repository references, readable text, safe motion, captions, CTA, and
  protected regions. The Director exposes an editable region surface and the
  validated contract is included in generation prompts without breaking older
  storyboards.
- Studio exposes an optional accessible spatial map and functional coordinate
  overlay. Edit, Context, and System retain one controller; the map is derived
  from visible semantic elements and does not retain pixels or create a second
  project model. Mobile controls retain 44-pixel targets and the overlay respects
  reduced-motion behavior inherited from Studio.
- Director now includes an integrated Prompting Studio tab. It exposes editable
  creative direction, Omni continuity, Veo continuity, Lyria music, and
  narration-guidance modules; exact read-only resolved scene, Veo-negative, and
  Gemini TTS inputs; model capabilities; consumer mapping; heuristic token
  estimates; draft history; warnings; and the resolved generation hash. Prompt
  preview does not dispatch media or emit prompt text to runtime telemetry.
- Generation idempotency now includes the exact resolved prompt-bundle revision,
  closing the prior case where a changed brief prompt with the same storyboard
  and attempt key could retrieve an older generation receipt.
- The production surfaces now share more of the same visual grammar: Prompting
  Studio shows the real branching video/music/narration topology, Queue shows
  truthful per-branch insertion counts, Media tiles expose actual observation
  state and bounded hashes, and Governance includes a receipt-backed
  verification console. These are projections of canonical data rather than
  simulated waveforms, fake progress, or generated interface labels.

- `npm run sag-server` starts only the authoritative FastAPI semantic engine on
  port 8080. Next.js remains a separate consumer.
- Equivalent SQLite migration 9 and PostgreSQL migration 5 add versioned event
  definitions, bounded runtime events, cursor indexes, and active Studio depth.
  SQLite migrations 10–11 and PostgreSQL migrations 6–7 add protected
  provider connections plus engine-owned delivery profiles, approvals, and
  publication attempts.
- SQLite migration 12 and PostgreSQL migration 8 add the provider-neutral
  `sag-journal/0.1-draft` kind registry, per-scope chain heads, and append-only
  tamper-evident entries.
- Event manifests reconcile by stable ID and source hash. Released schema drift
  fails closed. Payload redaction removes token, credential, prompt, secret,
  media-byte, and unrestricted-output fields before persistence.
- Cursor history, resumable SSE, keepalives, invalid/pruned-cursor reset,
  persisted polling fallback, and same-origin authenticated Next proxy routes
  are present. PostgreSQL uses LISTEN/NOTIFY only as a latency-reducing wake
  hint; persisted cursor polling remains the correctness path.
- Provider-neutral spatial contracts cover entities, edges, snapshots, deltas,
  viewport state, directives, and observed-effect ACKs. Projection IDs,
  hierarchy, X/Y/Z coordinates, causal edges, and hashes are deterministic.
- Snapshot, neighborhood, blast-radius, delta, runtime-history, runtime-stream,
  directive, and ACK HTTP endpoints are implemented with project/workspace
  scoping. MCP exposes snapshot, focus, hierarchy, neighborhood, blast radius,
  directive dispatch, and receipt verification over the same API.
- Registry coverage is checked at application startup. Redo now walks explicit
  canonical history rather than toggling undo, and magnetic/ripple moves use
  the same declared timeline command across HTTP, CLI, MCP, and Studio.
- Studio has persistent Edit, Context, and System depths. Selection,
  breadcrumbs, hierarchy, inspector, runtime state, Codex pause, and directive
  ACKs share one controller. Context/System use an accessible keyboard tree and
  optionally load React Three Fiber 9, Drei, and Three.js in separate chunks.
- Portrait mobile defaults to the complete semantic tree. WebGL absence or
  renderer failure leaves the hierarchy and inspector available.
- Browser capture uses OPFS chunk spooling with interrupted-file recovery when
  supported and a bounded 96 MB memory fallback otherwise.
- Governance now surfaces real delivery profiles, release approvals,
  publication-attempt counts, actors, scopes, and causal receipts without
  exposing secrets.
- Provider-neutral BYOK connection metadata and protected ciphertext live in
  the engine. Secret material is service-only and excluded from runtime events,
  receipts, and spatial metadata.
- Release approval and dispatch remain human/scoped gates in Next, but their
  canonical rows and receipts now live in the engine. The old Prisma delivery
  tables are legacy migration sources only; `pnpm migrate:delivery` previews an
  idempotent service-only transfer and `pnpm migrate:delivery -- --apply`
  performs it.
- The SAG-owned half of X1 now has a draft adapter and executable fixtures:
  stable `sag://` entity URIs, digest-derived edge URIs, bounded provenance,
  canonical graph hashes, and deterministic URI-based structural neighborhoods.
  It is explicitly `0.1-draft`; framework-owned `rrf_sources` and
  `sag.context_load` schemas plus the remaining journal freeze decisions must
  reconcile before this is called shared X1.
- The independent SAG journal adapter now reproduces all four framework
  `sqlite3-sag` fixtures byte-for-byte: both pinned clean hashes, duplicate-ID
  no-op, content tamper detection, and sequence-gap detection. Production
  namespaces use the complete canonical `scope_uri`; register-before-emit and
  no-float/no-bytes/credential payload gates are enforced. This observes the
  delivered X1-CLAUDE-002 fixture subset, while the four joint-freeze questions
  and broader X1 contract remain draft.
- The newly delivered X1-CLAUDE-001/003 schemas are consumed through bounded
  `RRFSourceEvidence`, `ContextNodeReceipt`, and `ContextLoadReceipt` models.
  Contract discovery publishes their JSON schemas; kept context nodes require
  anchors and non-empty evidence, and selection receipts enforce budget sums,
  blind-load savings, and ordered anchors. Four newly frozen journal §13
  fixtures also pass independently: Unicode-distinct content, float refusal,
  canonical namespace binding, and receipt/observation metadata round-trip.

Fresh evidence on this worktree: the full Python suite passes with one expected
skip, Prisma validates and generates, TypeScript typecheck passes, the
production Next build succeeds, and the Studio first-load route excludes the
separate 3D chunks.

Still pending before the complete release-candidate story can be claimed:

- live PostgreSQL LISTEN/NOTIFY wakeup and multi-instance latency evidence;
- a browser E2E suite at 375, 768, 1024, and 1440 pixels plus screen-reader and
  WebGL context-loss runs;
- live PostgreSQL verification of retained-revision spatial deltas and pruning
  reset behavior (the SQLite implementation and fixtures pass locally);
- execution and reconciliation of the legacy Prisma delivery migration against
  a backed-up staging database;
- framework-side X1 schema delivery and cross-implementation fixture
  reconciliation (the SAG-only draft adapter is locally green, not shared-observed);
- live end-to-end import, edit, render, verification, release, publication,
  Codex directive, ACK, reconnect, and mobile acceptance evidence.

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

The production implementation now includes the Python PostgreSQL repository,
provider-neutral filesystem/GCS blob storage, one-shot intake/analysis/render/
observer jobs, and a resumable SQLite/filesystem importer. Canonical jobs freeze
versioned inputs, are claimed transactionally, heartbeat leases, honor
cancellation, and dispatch observation under a separately permissioned identity.
Render output is promoted under an immutable GCS generation and independently
checked for bytes, media shape, decoded frames, audio, captions, and loudness.

This is still not externally admissible. Terraform deliberately defaults both
cloud execution and public admission off, and refuses public admission without
regional Cloud SQL HA. A correctly isolated staging GCP project must still pass
the real image builds, importer drill, English/Hebrew creator loop, restart and
persistence check, ten-workspace/two-heavy-job load test, backup restore drill,
and exactly-once private YouTube retry scenario.

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
  render-spec `sag-render-0.3` support.
- Browser, HTTP, CLI, and MCP generation, review, acceptance, caption, crop,
  render, cancellation, and receipt surfaces.

## Verification

- The local suite now covers the complete engine contract, storage immutability,
  importer planning, and identical SQLite/PostgreSQL repository behavior. The
  PostgreSQL gate also contests one job from two connections to prove an atomic
  claim.
- A fresh Prisma migration was applied to PostgreSQL and exercised with the real
  generated client. Cloud Build now repeats both Prisma-owned control migrations
  and Python-owned SAG migrations before building all three production images.
- Cloud acceptance and load harnesses are checked into `scripts/`; their reports
  are runtime evidence and must not be substituted by local mocks.
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
a curated human clip-quality benchmark, and longer target-phone thermal
testing. Output caption-contrast and integrated-loudness predicates are now
part of independent observation.

## Protected screen composites

The first evidence-safe generated-motion primitive is implemented as
`sag-protected-screen-composite/1.0`:

- A record binds an approved immutable screenshot capture, the generated plate,
  the audio-free composite output, the source crop, and the tracking-report hash.
- Creation blocks weak tracking, excessive untracked gaps, out-of-bounds crops,
  mismatched frame counts, invalid managed media, and composite-owned audio.
- Approval is a human Studio decision pinned to the exact project revision.
  Insertion is a separate confirmation-bound Studio command and is absent from
  MCP-eligible command surfaces.
- The canonical timeline retains the composite record ID. SQLite migration 16
  preserves that relationship across revisions and restarts.
- Render spec `sag-render-0.3`, artifact provenance, and QC preserve the source,
  recipe, plate, output, and tracking hashes. Generated surroundings remain
  decorative; only the protected screenshot region may satisfy product claims.
- Studio Review shows the tracked output beside its authentic source, exposes
  tracking coverage/gap evidence, and supports reject, approve, and insert.

Automated coverage proves weak-tracking rejection, missing-confirmation denial,
exact-revision approval, persisted insertion, audio-free FFmpeg compilation, and
frozen render lineage.

The July 29 local dogfood also passed the actual Studio-backed path with the
July 28 Omni proof: managed screenshot/plate/composite intake, screenshot and
composite decisions, exact-confirmation insertion, render, independent QC, and
sequence-bound artifact/receipt downloads. Artifact
`artifact_6e65381cbcf94466` and receipt `receipt_68c6280e9d394393` reproduced
SHA-256 `36b0b239610ef2331899eb4a231043c1c811fd05ccc7b8bf51934b4431e73d35`.
The detailed lineage and acceptance evidence are recorded in
`docs/progress/PROTECTED_SCREEN_COMPOSITE_DOGFOOD_2026-07-29.md`.

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

Production admission order:

1. Build immutable images and apply migrations in an isolated staging project.
2. Dry-run, import, resume, and verify a copy of the current local database and
   media roots.
3. Run the English/Hebrew cloud creator-loop harness, restart all services, and
   confirm the same revisions, receipts, artifact hashes, and observations.
4. Run the ten-workspace isolation/fairness test and a Cloud SQL restore drill.
5. Prove a simulated ambiguous retry produces exactly one private YouTube video.
6. Admit three internal workspaces, review monitoring and cost for a week, then
   consider expanding to ten.
