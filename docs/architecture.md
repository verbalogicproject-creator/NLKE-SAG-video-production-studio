# SAG Video architecture

```text
Browser GUI ─┐
CLI ─────────┼─ typed command API ─ revisioned project/event store
MCP tools ───┘                         │
                                       ├─ edit readback receipt
                                       │
                                       └─ frozen render specification
                                                   │
                                           FFmpeg controller
                                                   │ artifact + hash
                                                   ▼
                                            frame observer
                                                   │
                                       observed success/failure receipt
```

The server is authoritative for project state. The browser projects that state
into a timeline and monitor; it does not persist a private project model.
Every mutation supplies an expected revision and request ID. A stale actor
cannot overwrite a newer GUI or terminal edit, and a retried request cannot
apply twice.

## SAG Spatial Runtime

Spatial awareness is an application-owned semantic projection, not pixel
perception and not a second editor database. The FastAPI engine projects the
same canonical workspace, project, sequence, assets, tracks, timeline items,
jobs, artifacts, actors, and receipts used by HTTP, CLI, and MCP.

```text
canonical repositories
        |
        +-- deterministic hierarchy and coordinates
        |       X sequence time
        |       Y track or lifecycle ordering
        |       Z creation -> composition -> runtime -> governance -> delivery
        |
        +-- persisted runtime-event cursor
        |       -> bounded history
        |       -> resumable SSE
        |
        +-- governed spatial directives
                accepted -> awaiting_consumer -> observed_success/failure/timeout
```

`SpatialSnapshot` is reproducible for the same canonical revision and focus.
Coordinates, entity IDs, causal edges, and the projection hash are computed by
the engine. Browser camera, filters, collapsed groups, renderer choice, and the
last selected Edit/Context/System depth are viewport state only.

The default Context projection is the selected identity plus two relationship
hops, capped at 200 entities and 400 edges. System requests a production-wide
projection within the same hard limits. The ordinary DOM hierarchy,
breadcrumbs, and polymorphic inspector use the identical snapshot as the
lazy-loaded React Three Fiber renderer. WebGL is never required to identify or
operate an entity.

Runtime events are separate from durable timeline mutation events. SQLite
migration 9 and PostgreSQL migration 5 add versioned event definitions and a
numeric runtime cursor. Repository manifests reconcile by stable kind and
source hash; released schema drift fails startup. Payloads are recursively
sanitized and size bounded. Runtime telemetry expires after seven days and is
capped at 50,000 rows per project. Durable commands, receipts, artifacts, and
approvals retain their own policies.

SSE treats persisted cursor rows as truth. Local wake notifications only reduce
latency; timed cursor checks recover lost notifications and cross-instance
writes. `Last-Event-ID` and an explicit cursor resume a stream. An invalid or
pruned cursor emits `snapshot_required`. Commands remain request/response REST.

Delivery and provider governance use the same authority boundary. Protected
provider ciphertext is engine-owned, readable only by an authenticated service,
and never enters telemetry or spatial metadata. Delivery profiles, release
approvals, and publication attempts are also engine-owned and therefore appear
in the deterministic System projection. Next enforces the human browser gate
for approval and creates signed downloads, but it does not keep a competing
canonical approval or attempt row. Approval receipts bind the exact revision,
verified artifact hashes, destinations, actor, and request ID; dispatch consumes
that approval exactly once.

Spatial actions accept stable semantic IDs only. They never accept DOM
selectors, camera matrices, pointer coordinates, or synthesized clicks. The
browser can pause agent-driven view changes while keeping read-only context
available. A directive is not reported as visible until the browser returns a
matching projection hash, exact observed target IDs, active depth, renderer
mode, and bounded findings.

## X1 semantic graph adapter (draft)

The engine exposes a provider-neutral draft adapter at
`/api/projects/{id}/semantic/graph` and
`/api/projects/{id}/semantic/neighborhood`. It derives from `SpatialSnapshot`;
it does not store another graph. Local identities remain unchanged while the
adapter adds stable NFC-normalized, percent-encoded `sag://` URIs, digest-based
edge identities, bounded provenance anchors, and deterministic structural
traversal. Geometry remains under the `sag.video.spatial` extension.

The adapter refuses unknown seeds, scopes, relationship kinds, incompatible
revision authorities, and historical requests whose mixed runtime/governance
continuity cannot be proven. Its `0.1-draft` label is intentional: the
framework-owned `rrf_sources` and `sag.context_load` receipt are not invented
here. The journal protocol now passes the delivered reference fixtures, but
its remaining joint-freeze decisions and those schemas must reconcile before
X1 is frozen.

## Durable causal journal (X1 draft)

The engine independently implements `sag-journal/0.1-draft`; it does not import
the `sqlite3-sag` reference package. SQLite migration 12 and PostgreSQL
migration 8 add a registered kind manifest, per-namespace locked chain head,
and append-only entries carrying `seq`, `prev_hash`, `row_hash`, and hash
algorithm. The canonical preimage uses sorted compact UTF-8 JSON and matches
the framework fixtures byte-for-byte.

Project streams use their complete canonical X1 `scope_uri` as the namespace.
Duplicate IDs are no-ops that do not advance the head. Undeclared kinds,
unbounded content, floats, bytes, and credential markers are refused before
hashing. Verification walks sequence order and reports the first sequence gap,
predecessor mismatch, or row-hash mismatch. Runtime telemetry remains in its
separate expiring cursor store and is never promoted into the journal.

Journal append/list/verify are available through scoped HTTP, direct MCP, and
the authenticated Next MCP boundary. Existing controller tables remain
authoritative for operations until the shared receipt/observation metadata
round-trip fixture is frozen; the adapter does not silently mirror records into
an unsettled wire format.

The embedded SQLite implementation is normalized and migration-driven. Project heads,
revision headers, revisioned assets/tracks/items, semantic events, receipt
transitions, and observation findings are queryable rows rather than serialized
project/event blobs. One unit of work commits the revision, event, receipt, and
observation atomically. Jobs and provider runs sit behind storage-neutral
repository protocols; see `persistence-spec.md` for the table/query contract.

The X1 retrieval/context seam is consumed as a bounded contract rather than a second retrieval
engine. `RRFSourceEvidence` admits only declared `rrf_sources` labels and a fused score; kept
`ContextNodeReceipt` records require a source anchor and non-empty evidence, while dropped nodes
must explain their decision. `ContextLoadReceipt` enforces the hard token budget, kept-node token
sum, blind-load savings, and ordered anchors. The engine exposes these schemas through `/api/contract`
and excludes raw prompts, file contents, embeddings, and unrestricted model output.

The SAG adapter reproduces the four newly frozen journal §13 fixtures (`unicode_distinct`,
`refuse_float_metadata`, `namespace_scoped`, and `receipt_observation_roundtrip`) in addition to
the original four. The journal remains `sag-journal/0.1-draft` until both providers pass the full
fixture set; this is an observed conformance result, not a protocol rename.

## Short discovery boundary

`shorts.generate` freezes a source revision, asset hash, prompt, language, and
duration settings. A separately runnable analysis worker extracts 16 kHz audio,
obtains real word timestamps from local whisper.cpp or a configured remote
Whisper endpoint, measures silence and scene changes with FFmpeg, and uses
MediaPipe face tracks when that optional runtime is installed. Missing
transcription capability is an actionable failure; transcript text is never
fabricated as a fallback.

Candidate scoring is deterministic by default. An OpenAI-compatible structured
output adapter may adjust hook, flow, and value components, but model output is
bounded to existing candidate IDs and validated before persistence. Accepted
suggestions create sibling projects in the same workspace. Project-scoped asset
IDs reference the same SHA-256 media blob, so source bytes are not copied and
paired identities can access source and derived projects without gaining
cross-workspace authority.

Caption words/styles and crop keyframes are normalized revision children.
Render spec `sag-render-0.2` compiles them into libass karaoke captions,
time-varying crop expressions, stable two-person split layouts, and normalized
audio. The render observer remains the authority for output success.

## Declared application contract

`GET /api/contract` is generated from the same command registry used by the
dispatcher. It publishes stable entity identity rules, typed argument schemas,
revision/effect behavior, required scope, and read-only runtime capabilities.
`GET /api/projects/{id}/commands/active` filters that declaration for current
project state. Neither endpoint grants authority; authentication, exact
revision, target state, and arguments are evaluated again on invocation.

## Managed-media intake

```text
browser picker / CLI-selected file
        │ streamed bytes, not a server path
        ▼
managed staging → SHA-256 → ffprobe limits
        │
        ├─ invalid → observed_failure + temporary-file removal
        │
        └─ valid → opaque source identity
                    ├─ phone proxy
                    ├─ thumbnail/waveform
                    └─ canonical project revision + receipt
```

Managed URIs are opaque API identities. Absolute media/proxy paths remain
server-side, and artifact retrieval is project scoped. Content-identical
imports reuse the existing observed-valid asset and disclose deduplication in a
new receipt rather than creating a confusing second identity.

The intake observation shares the local service failure domain and says so.
Independent media validation is deferred; it must not be implied by successful
ffprobe/FFmpeg work in the same deployment.

Editing receipts use canonical state readback and disclose that the readback is
not an independent failure domain. Rendering uses a stricter boundary. The HTTP
request freezes an exact revision and source hashes into a persistent job, then
returns an accepted receipt. One bounded worker builds an allowlisted FFmpeg
graph from managed inputs, atomically finalizes and hashes the output, and hands
it to observation. The controller exit code is not proof of the intended output.

When a title exists, its declared plate color supplies a bounded safe-area
predicate over a decoded frame. A production observer should add OCR, caption
coverage, loudness, silence,
black-frame, frozen-frame, and brand-template predicates while continuing to
report uncertainty as failure or inconclusive, never success.

## GCP execution boundary

The control plane writes a canonical job and queue outbox row in one PostgreSQL
transaction. Reconciliation converts pending outbox rows into OIDC-authenticated
Cloud Tasks calls. The private dispatcher atomically claims the canonical job
before starting the allowlisted Cloud Run Job with only that job ID. Duplicate
tasks therefore do not duplicate heavy work.

Browser-facing media identities remain `sag-blob://` and `sag-artifact://`.
Only server-side storage rows contain GCS bucket, key, and generation. A direct
upload is promoted only after generation, byte size, MIME type, workspace, and
quota checks. Intake still hashes and probes the bytes independently.

Publishing is limited to YouTube private visibility. OAuth tokens are encrypted
with workspace and channel bound KMS associated data. A publication job needs a
verified artifact and a short-lived, single-use human approval bound to the
artifact SHA, channel, and private visibility.

## Current receipt vocabulary

Nonterminal: `accepted`, `awaiting_consumer`, `dispatched`, `rendering`,
`artifact_written`, `awaiting_observation`, and `awaiting_approval`.

Terminal: `observed_success`, `observed_failure`, `execution_failed`, `denied`,
and `timeout`.

Receipts bind the request ID, actor, exact project revision, controller,
artifact hash, observation findings, and observer deployment mode.
