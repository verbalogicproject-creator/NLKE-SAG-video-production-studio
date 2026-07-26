# SAG Video current state snapshot

Captured: July 23, 2026 at 16:28 IDT (UTC+03:00)

Repository branch: `main`
Base commit: `3b0221c96113` (`feat: add GCP beta control plane foundation`)

## Executive status

SAG Video is ready for local, internal dogfooding of the editor, media intake,
shorts analysis, focused edits, rendering, independent observation, and receipt
flow. The July 23 mobile repair makes the Python editor usable as a true
four-pane phone interface and corrects the false `Timeline gap` state shown for
generated demo clips.

The production GCP architecture is substantially implemented in the current
working tree, including the Python PostgreSQL repository, provider-neutral
filesystem/GCS storage, canonical one-shot Cloud Run job entrypoint, and
resumable importer. These were previously identified as code blockers and are
no longer missing implementation slices.

The system is **not ready for external beta admission**. Real container builds,
an isolated staging deployment, importer and restore drills, cloud creator-loop
acceptance, load/isolation evidence, and the exactly-once private YouTube retry
test remain mandatory gates. Terraform keeps cloud execution and public
admission disabled by default.

## State at a glance

| Area | Current state | Evidence or remaining gate |
| --- | --- | --- |
| Local Termux workflow | Dogfood-ready | Local PostgreSQL, filesystem storage, engine, observer, and Chamber launcher are present. |
| Phone editor | Working slice | True mobile panes, corrected monitor state, fixed timeline scrolling, narrow-header layout, and touch-sized controls are implemented. |
| Media intake | Implemented | Bounded upload, hashing, ffprobe observation, proxy and thumbnail generation, opaque identities, deduplication, and receipts. |
| Shorts workflow | Implemented locally | Transcription, ranking fallback, distinct candidate generation, captions, crop plans, focused edits, and acceptance surfaces. |
| Rendering | Implemented locally | Revision-bound FFmpeg render specs, immutable artifact finalization, cancellation, and persistent job state. |
| Independent observation | Implemented | Hash, dimensions, duration, decoded frames, audio, captions, and loudness predicates. |
| PostgreSQL SAG repository | Implemented | Python-owned migrations, normalized revisions, transactional work, leases, atomic claims, and SQLite/PostgreSQL parity coverage. |
| GCS adapter | Implemented | Provider-neutral blob interface, generation preconditions, immutable promotion, hash checks, and filesystem fallback. |
| Heavy Cloud Run job runner | Implemented | One-shot canonical-ID entrypoint for intake, analysis, render, and observer roles. |
| Local-to-cloud importer | Implemented | Plan, run, resume, and verify modes with workspace mapping, advisory locking, checkpoints, and reports. |
| GCP control plane | Implemented foundation | Cloud Run, Cloud SQL, GCS, Tasks, Scheduler, KMS, Secret Manager, Artifact Registry, Monitoring, IAM identities, and quotas are represented. |
| Hosted MCP | Implemented foundation | Authenticated project discovery, review, edit, render, evidence, approval, download, and publication tools. Real hosted acceptance is pending. |
| Private YouTube publishing | Implemented foundation | KMS-encrypted OAuth storage, single-use approval binding, forced private visibility, resumable upload, and retry reconciliation. Real acceptance is pending. |
| External beta | Blocked by admission gates | Cloud execution, HA, acceptance, load, restore, monitoring, and YouTube evidence must pass first. |

## July 23 mobile editor repair

The phone screenshot exposed several independent defects that combined to make
the editor appear nonfunctional:

- The bottom navigation only scrolled to desktop panels instead of selecting a
  single mobile pane.
- The whole timeline, including its toolbar and labels, scrolled horizontally.
- Generated fixture clips without a managed media URI were excluded from
  timeline playback and reported as gaps.
- Title and caption visibility was not updated before returning from a gap.
- The ruler width did not align with the track lanes.
- The header action row could overflow on narrow Android viewports.

The current working tree now:

- treats Media, Monitor, Timeline, and Inspector as real mobile tabs;
- remembers the selected pane for the browser session;
- keeps timeline edit and zoom controls fixed while only track content scrolls;
- keeps track labels visible at the left edge of the timeline scroller;
- shows a clearly labeled preview-only slate for generated demo media;
- synchronizes generated and managed clips without redrawing every animation
  frame;
- applies half-open title and caption ranges consistently;
- aligns the ruler with the track lane coordinate system; and
- stacks the phone header into non-overflowing rows at 430 CSS pixels and below.

The built-in `Verified developer demo` remains a diagnostic fixture. Its title
is deliberately clipped and its early clips are generated slates, so visual
quality dogfooding should use a new project with imported real media.

## Implemented production architecture

### Persistence and storage

- Prisma owns control-plane and queue migrations.
- Python owns normalized SAG migrations and checksum verification.
- SQLite remains available for embedded tests; PostgreSQL is the local and
  production repository target.
- Canonical jobs freeze versioned inputs and use transactional claims,
  heartbeats, cancellation, retry leases, and duplicate-safe completion.
- Blob identities remain opaque to domain contracts.
- Filesystem and GCS storage share a provider-neutral interface.
- The importer excludes local bearer tokens and Codex pairing state by design.

### Execution and isolation

- The public Chamber and private engine are modeled as separate Cloud Run
  services.
- Intake, analysis, rendering, and observation run as separately dispatched
  one-shot jobs.
- Workers receive only a canonical job ID; job kind and runtime arguments are
  fixed by infrastructure.
- Canonical job and transactional outbox state are persisted before dispatch.
- Cloud Tasks invokes the private dispatcher with OIDC authentication.
- Scheduler reconciliation handles undispatched and expired work.
- Web, engine, dispatcher, workers, and observer use separate service accounts.
- Workspace authorization is enforced across control records, media keys,
  jobs, receipts, MCP, and downloads.

### Product and safety controls

- Invite-only Google identity and workspace roles are represented.
- Owner-managed API keys are stored as hashes and carry explicit scopes.
- Mutations use expected revisions, request IDs, idempotency, and causal
  receipts.
- Publishing requires a single-use human approval bound to workspace, artifact
  SHA-256, channel, and private visibility.
- Render output is staged, promoted immutably, and observed under a separately
  permissioned identity before it becomes downloadable or publishable.
- Upload, storage, concurrency, daily render, and cleanup quotas are modeled.

## Verification captured for this snapshot

Fresh checks completed against the current mobile-editor working tree:

- Full Python engine suite passed with one expected skip.
- The 12 targeted editor and media-intake tests passed.
- JavaScript syntax validation passed for the static editor.
- `git diff --check` passed.
- The static document contains unique element IDs and valid pane references.

The full suite emitted two non-failing upstream/deprecation warnings:

- Starlette's legacy `httpx` TestClient integration is deprecated.
- Pillow's `Image.getdata()` is scheduled for removal in Pillow 14.

Previously documented repository evidence includes:

- SQLite/PostgreSQL repository parity and a contested atomic PostgreSQL claim;
- a fresh Prisma migration applied with the generated client;
- Python SAG migration coverage;
- real local H.264/AAC import, proxy, thumbnail, render, and observation;
- Hebrew/English title and active-caption FFmpeg renders; and
- importer planning, storage immutability, reconstruction, rollback, recovery,
  integrity, and foreign-key coverage.

This snapshot does **not** claim fresh successful evidence for the current
working tree's production container builds or live GCP acceptance. Those remain
explicit gates below.

## Working-tree condition

This snapshot describes an active, uncommitted implementation state rather than
a release commit.

- 40 tracked files are modified.
- 14 untracked entries are present.
- The tracked diff contains approximately 945 insertions and 159 deletions.
- The untracked implementation includes the PostgreSQL repository, blob
  storage, cloud job runner, importer, repository factory, migrations, parity
  tests, cloud acceptance harness, load harness, and cleanup route.

No secrets or runtime database contents are intentionally included in this
snapshot. Before creating a release candidate, audit the complete diff, verify
ignored runtime paths, group the work into reviewable commits, and record the
resulting immutable commit and image digests.

## Current dogfood boundary

Internal local dogfooding can begin now with this loop:

1. Start the Termux stack with `sh scripts/dev-termux.sh`.
2. Open `http://127.0.0.1:3000/dashboard`.
3. Create a new project rather than judging the diagnostic demo.
4. Import a real English or Hebrew video.
5. Verify thumbnail, proxy playback, seeking, and timeline insertion.
6. Generate and compare three distinct platform drafts.
7. Apply trim, title/hook, captions, crop, gain, and mute edits.
8. Render and wait for independent observation.
9. Download the verified artifact and compare its SHA-256 to recorded evidence.
10. Restart local services and confirm the project, revision, receipts,
   artifacts, and observation persist.

Manual phone checks still worth recording are landscape behavior, real proxy
playback across clip boundaries, seeking, split/drag/delete/undo, long-session
thermal behavior, and Hebrew input/edit ergonomics.

## Remaining production admission gates

Complete these in order in a dedicated staging GCP project:

1. Review and commit the working tree; attach a clean validation report.
2. Build immutable web, engine, and jobs images through Cloud Build.
3. Apply Prisma and Python migrations to an isolated staging Cloud SQL
   instance.
4. Run importer plan, interrupted run/resume, and verification against a
   consistent copy of the current SQLite database and media roots.
5. Enable cloud execution while keeping external admission disabled.
6. Run the English and Hebrew creator-loop acceptance harness through GCS,
   Cloud Tasks, Cloud Run Jobs, independent observation, and signed download.
7. Restart every service and verify revisions, receipts, artifact hashes, and
   observations are unchanged.
8. Run the ten-workspace load/isolation test and prove no more than two heavy
   jobs execute concurrently with fair tenant progress.
9. Restore a Cloud SQL backup into a separate instance and compare record
   counts and artifact identities.
10. Simulate an ambiguous YouTube timeout and prove one human approval produces
    exactly one private video.
11. Enable regional Cloud SQL HA, verify monitoring/budget alerts, and admit
    three internal workspaces.
12. Review reliability, failures, queue behavior, quota use, storage, and cost
    for one week before considering expansion to ten workspaces.

## Infrastructure safety state

Terraform currently defaults to:

- `enable_cloud_execution = false`
- `external_beta_enabled = false`
- `cloud_sql_ha = false`

It rejects external admission unless both cloud execution and regional Cloud
SQL HA are enabled. These defaults must remain closed until every production
admission gate has runtime evidence.

## Recommended immediate next action

Run one complete real-media local dogfood session on the target Android phone,
capture failures and usability friction, and then freeze a clean repository
candidate for real Cloud Build validation. Do not enable Terraform job resources
for external users until the staging importer, cloud acceptance, load, restore,
and YouTube exactly-once gates pass.
