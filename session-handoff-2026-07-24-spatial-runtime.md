# SAG Video implementation handoff — 2026-07-24

## Resume instruction

Read this file completely, then continue the existing implementation in
`/data/data/com.termux/files/home/openai/sag-video`. Do not restart the design
process and do not discard the dirty worktree. The uncommitted changes include
both the user's existing cloud work and the current SAG Video implementation.

## Product objective

Build SAG Video as a production-capable video studio that can be operated
through either the human frontend or Codex through SAG. Both actors must use
the same semantic action registry, authoritative state, scoped permissions,
confirmation gates, and receipts.

The canonical frontend is Next.js. FastAPI remains the authoritative editing,
media, action, pairing, and receipt engine. The initial product wedge is a
reliable long-video-to-short-form workflow with professional manual editing,
render verification, and bounded multi-platform delivery.

## Locked authority model

- Sequence-scoped grants are the default.
- Codex may inspect, analyze, propose, execute safe reversible edits, run
  atomic edit batches, render, verify, and prepare release bundles.
- Upload/capture permissions, OAuth connection, destructive confirmations,
  release approval, and public promotion remain human-only.
- A normal successful edit is `committed`, not `observed`. Observation requires
  an independent consumer/failure domain.
- Exact confirmations are single-use, hashed, scoped, and revision-bound.
- Database metadata may select allow-listed handlers but cannot supply code.

## Implemented in this worktree

### Engine and registry

- Schema version 8 and PostgreSQL parity additions for scoped pairing,
  confirmations, and actor-local focus.
- Versioned command/action declarations with handler keys, scopes, safety
  classes, confirmation policies, eligibility, stable IDs, and deterministic
  source hashes.
- Shared action gateway with scope enforcement and handler allow-list checks.
- Read-only proposals and atomic command batches with one canonical revision.
- Exact human confirmation for destructive timeline deletion.
- Actor-local selection and an explicit shared-focus action.
- Bounded context projection containing sequence, focus, surface/workflow,
  authority, and effective eligibility.
- MCP and CLI support for context, catalog, proposals, batches, actions, focus,
  and receipts.

### Canonical Studio

- New route: `/projects/[id]/studio/[sequenceId]`.
- Responsive professional editor with media panel, managed preview, inspector,
  multitrack timeline, activity/receipt drawer, pairing, render, and short-form
  suggestions.
- Browser capture for screen, camera, microphone, and screen plus camera with
  explicit permissions, bounded duration/size, and managed uploads.
- Authenticated managed-asset proxy with byte-range forwarding.
- Shared Studio API used by the frontend controller.
- Prisma models and migration for sequences, delivery profiles, release bundle
  approvals, and publication attempts.
- Generic release API that verifies artifact hashes and sequence revision,
  requires human approval, records idempotent attempts, and provides an honest
  signed-download fallback when a provider adapter is unavailable.
- Hosted MCP now resolves exact sequences and uses the effective registry.

### Verification already completed

- Full Python engine test suite passed, with one expected skip.
- Prisma schema validation passed.
- Prisma client generation passed.
- TypeScript typecheck passed after the Studio and release changes.

## Spatial Runtime insight

The architectural input is:

`/storage/emulated/0/Download/claude-projects/aria-personal/docs/the-game/shooter-matrix.html`

The prototype is a 590-line browser-local 2D canvas game. Its important
mechanics are not its shooter appearance:

- a logical 5 by 10 runtime state matrix separate from rendering;
- deterministic screen-to-grid and grid-to-screen projection;
- a continuous state/update/render loop;
- player, enemy, and projectile state represented separately;
- a director state machine for analyzing, predicting, and reconciling actions;
- coordinates used as a shared reference for input and diagnostics.

Its present limitations are equally important: the “server-side authority” and
“AI Director” are browser-local, identities are ephemeral, `highlightCell`
only logs, and there is no real registry, scope, revision, or receipt boundary.

### Correct interpretation

Upgrading this to 3D can give SAG spatial runtime awareness, but 3D rendering
alone does not create awareness. The new scene must be a deterministic
projection of authoritative semantic state. Each visible entity needs:

1. a stable semantic ID and optional repository/runtime URI;
2. kind, label, bounds, transform, and spatial/topological relationships;
3. current revision and bounded live state;
4. actor-local selection plus explicitly shared focus;
5. eligible registry actions and safety/confirmation classification;
6. causal edges to source assets, jobs, outputs, approvals, and receipts;
7. acknowledgements proving whether a requested visual/runtime effect was
   actually consumed.

This makes the scene a shared address space. A human can point at an entity;
Codex can resolve the same stable identity without inferring from pixels.
Codex can ask what is selected, visible, adjacent, upstream, downstream, or in
the blast radius, and may request only governed semantic actions. The browser
then acknowledges the observed effect through the receipt system.

That is the mechanism behind “seeing runtime”: not computer vision and not a
model embedded inside the application, but a live application describing its
own state and affordances through the same controlled semantic surface used to
operate it.

### SAG Video projection

Keep the conventional 2D timeline as the primary editing workspace. Add a
separate optional **Spatial Runtime** view rather than replacing the timeline.
One useful initial mapping is:

- X: sequence time;
- Y: tracks, layers, and delivery lanes;
- Z: provenance and runtime depth (source asset -> edit -> render -> delivery);
- entities: clips, captions, effects, analysis suggestions, render jobs,
  artifacts, actors, approvals, attempts, and receipts;
- edges: consumes, derives-from, overlaps, blocks, confirms, renders-to, and
  publishes-to.

Selecting a clip could reveal its source asset, dependent captions/effects,
render outputs, delivery crops, and receipts. Selecting a failing render could
reveal its exact inputs, revision, worker attempt, and downstream releases.
This is a practical spatial debugger and causal/provenance view, not decorative
3D.

### Minimal first conformance slice

1. Define a provider-neutral `SpatialEntity`, `SpatialEdge`, `SpatialSnapshot`,
   `SpatialDelta`, and `ViewportState` contract.
2. Project the existing Studio sequence, clips, tracks, render jobs, artifacts,
   and receipts into that contract using stable existing IDs.
3. Add read-only engine endpoints and MCP tools for snapshot, delta, selection,
   neighborhood, and blast radius.
4. Render the projection in a lazy-loaded 3D Studio pane with accessible list
   parity and a 2D fallback.
5. Route selection through actor-local focus; require explicit action to share
   browser focus.
6. Add only reversible camera/focus/reveal actions initially and require an
   observed-effect ACK from the browser.
7. Prove deterministic projection, bounded deltas, revision consistency,
   keyboard navigation, reduced motion, and mobile fallback in tests.

Avoid introducing Three.js or another dependency until the semantic contracts
and test projection exist. The contract is the architecture; the renderer is
replaceable.

## Immediate implementation queue

Before starting the 3D renderer, finish and verify the current Studio vertical
slice:

1. Inspect and complete the CLI patch for `action propose` and `action batch`.
2. Run the full Python suite again, TypeScript typecheck, and production Next
   build.
3. Add a build-time action coverage gate and controller parity tests.
4. Implement undo/redo parity and timeline ripple/magnetic edit commands.
5. Add OPFS capture spooling/fallback and capture failure recovery.
6. Surface delivery profiles, release approval, and publication attempts in
   Studio.
7. Add provider-neutral BYOK connection UI and keep secrets outside receipts.
8. Add browser tests for desktop/mobile layouts, keyboard operation, focus,
   range playback, pairing continuity, and receipt state changes.
9. Update implementation-status and architecture documentation honestly,
   separating demonstrated, implemented-unverified, and proposed capabilities.
10. Then implement the Spatial Runtime contract and read-only projection slice
    above before selecting a renderer.

## Important gaps still open

- No production Next build has been run after the latest work.
- No frontend browser/E2E suite exists yet.
- Redo and magnetic/ripple commands are incomplete.
- Capture is memory-backed; OPFS spooling is not implemented.
- Delivery/release controls are API-level and not yet surfaced in Studio.
- BYOK model connection UI is not implemented.
- TikTok/Instagram adapters are not implemented; fallback behavior is honest.
- Static FastAPI UI remains until Next reaches verified parity.
- Spatial Runtime is now formalized here but has not been implemented.

## Naming discipline

Use **SAG Spatial Runtime** for the shared semantic scene capability. Use
“spatial awareness” in explanatory prose, but do not claim model perception of
pixels or full world understanding. The precise claim is: SAG gives an agent a
bounded, live, semantically addressable projection of application runtime and a
governed way to act on it.
