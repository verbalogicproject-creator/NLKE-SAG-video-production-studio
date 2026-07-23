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

The embedded SQLite implementation is normalized and migration-driven. Project heads,
revision headers, revisioned assets/tracks/items, semantic events, receipt
transitions, and observation findings are queryable rows rather than serialized
project/event blobs. One unit of work commits the revision, event, receipt, and
observation atomically. Jobs and provider runs sit behind storage-neutral
repository protocols; see `persistence-spec.md` for the table/query contract.

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

Nonterminal: `accepted`, `dispatched`, `rendering`, `artifact_written`,
`awaiting_observation`, and `awaiting_approval`.

Terminal: `observed_success`, `observed_failure`, `execution_failed`, `denied`,
and `timeout`.

Receipts bind the request ID, actor, exact project revision, controller,
artifact hash, observation findings, and observer deployment mode.
