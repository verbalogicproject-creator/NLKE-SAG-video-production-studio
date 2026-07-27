# SAG Computer-Use v1 implementation progress

Captured: July 27, 2026 (Asia/Jerusalem)

## Outcome

The workspace now contains a feature-gated, browser-wide, active-tab computer-use contract and a buildable Manifest V3 extension shell. It is designed as an authority-preserving observation/effect system, not a general browser automation surface.

Implemented:

- `sag-computer-use/1.0` and signed `sag-computer-use-profile/1.0` schemas;
- workspace-scoped activities, observations, intents, one-use execution tickets, executions, explicit image checkpoints, context attachments, and append-only effect receipts;
- exact-origin Ed25519 profile verification, anti-rollback, semantic bindings, bounded argument validation, safety classes, effect predicates, and declared compensation;
- navigation/origin/pause/close/expiry invalidation;
- browser-extension pairing principals with a dedicated `computer_use` audience and four narrow scopes;
- token audience isolation from project, render, delivery, approval, and publication endpoints;
- direct multipart checkpoint upload, static-image/MIME/dimension/decompression checks, metadata-stripped canonical PNG, original/canonical SHA-256, managed storage, direct download, 30-day expiry, and context retention;
- canonical `timeline.set_clip_transform` routing with exact project revision and underlying SAG receipt;
- FastAPI and MCP read/intent/execute/receipt surfaces;
- Studio **Pair browser** flow and stable semantic selected-clip/revision markers;
- active-tab Shadow DOM overlay with session-only state, generic metadata observation, signed-profile actions, explicit checkpoints, 0.85 scale acceptance, and 1.00 compensation;
- bundled local SAG and generic fixture profiles plus an external-private-key signing utility;
- contract documentation and a web-researched capability-intersection product report.

## Verification

- Full FastAPI engine suite: passed with one existing environment-dependent skip.
- Focused computer-use, pairing, migration, and contract tests: passed.
- Extension JavaScript syntax/typecheck: passed.
- Extension unpacked build: passed at `apps/nlke-sag-extension/dist` (ignored generated output).
- Lab web TypeScript typecheck: passed.
- Next.js optimized production build: passed with an explicit 4 GiB V8 heap after the default 2 GiB heap exhausted during build finalization.
- `git diff --check`: passed.
- Static profile signature verification: passed.
- Secret scan found no committed private signing key or rotated credential.

The automated acceptance proves signed profile install, browser-principal audience isolation, generic observation with zero actions, explicit before checkpoint, exact-revision scale `0.85`, ticket replay rejection, changed-state/revision effect receipt, explicit after checkpoint lineage, direct PNG download, and compensation to scale `1.00`.

## Honest remaining gate

This Termux/proot environment cannot run a desktop Chrome extension session. Loading the unpacked extension, granting its optional exact engine-origin permission, pairing from Studio, and exercising the visible overlay against live Studio remain a manual desktop Chromium dogfood gate. No claim of completed live Chrome acceptance is made.

## Product direction from research

The strongest wedge is **Verified Proof-to-Video**: a real semantic workflow plus explicit authentic checkpoints becomes a polished SAG production and a verifiable evidence package. Next-ranked intersections are transactional browser actions, active-tab UI/profile drift detection, reproducible incident capsules, local-redacted evidence, and Sol/Terra/Luna plan-execute-review delegation. Download intake and semantic tab recording with real audio are valuable but require separate contract amendments.

Detailed sources and prioritization are in `docs/research/NLKE_SAG_CHROME_EXTENSION_CAPABILITY_INTERSECTIONS.md`.

## Release boundary

The feature remains disabled by default behind `SAG_COMPUTER_USE_V1`. v1 intentionally excludes coordinates, arbitrary JavaScript, generic action execution on unsigned origins, silent/background browsing, continuous screenshot capture, unrestricted CDP, credential administration, approvals, rendering authority, delivery, and publication.
