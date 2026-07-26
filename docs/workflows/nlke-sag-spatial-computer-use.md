# NLKE-SAG spatial computer use

Status: additive experimental slice, `sag-spatial-frame/1.0`

This document is the evolving integration ledger for architectural and spatial
awareness in SAG Video. The objective is computer-use-like reliability without
making vision output authoritative. SAG Video is both the first consumer and
the calibration vessel: every declared frame, routed action, observed effect,
and verified receipt becomes evidence for improving the next cycle.

## Core invariant

The FastAPI engine, canonical repositories, revision checks, command registry,
and receipts remain authoritative. Spatial awareness is a binding and
observation plane over that state. It may locate and explain canonical entities;
it may not invent an entity, grant an action, bypass human consent, or directly
mutate project state.

```text
S0 canonical projection
  -> S1 viewport declaration
  -> S2 region binding and resolution
  -> S3 governed action proposal
  -> S4 semantic command or handler
  -> S5 fresh viewport observation
  -> S6 receipt reconciliation
  -> S0' verified state for the next cycle
```

The loop is recursive rather than circular: `S0'` carries new evidence and may
have a new canonical revision, runtime cursor, projection hash, visible layout,
or all four. Failed and ambiguous effects are observations too; they do not get
rewritten as success.

## Versioned frame contract

`SpatialFrame` contains only bounded metadata:

- canonical revision, System projection hash, runtime cursor, and active Studio
  depth;
- CSS viewport dimensions, device-pixel ratio, and scroll offsets;
- an engine-computed adaptive grid using 4-16 columns, 6-24 rows, an 80-pixel
  target, and a 44-pixel minimum cell size;
- normalized top-left rectangles in `[0,1]`, frame-local cells, stable entity
  and binding IDs, roles, labels, eligible actions, source, confidence,
  occlusion, protection, and bounded evidence references;
- a metadata-only, redacted, or not-applicable redaction declaration and an
  optional media hash.

Raw screenshots are intentionally absent and rejected as extra fields. Frame
events expire with bounded runtime telemetry. Cell identifiers are not stable
addresses and must never be stored as canonical project identity.

## Binding priority

1. DOM and accessibility geometry bound to declared `data-sag-entity-id`
   identities.
2. Canvas or manual region declarations reconciled to known canonical IDs.
3. Optional Gemini observation of explicitly redacted input.
4. Coordinate fallback only when separately enabled, confidence is at least
   `0.95`, and the action is not sensitive.

Resolution always returns canonical candidates sorted by confidence and region
specificity. Action eligibility is intersected with the engine declaration;
the observer cannot claim additional capability.

## Action and observation

A frame-bound directive names the expected frame and binding in addition to the
existing expected revision and projection hash. Studio resolves that binding to
an existing semantic handler. After interaction it declares a fresh frame and
ACKs with the before and after IDs, observed targets, changed entities and
cells, renderer, active depth, findings, and exact action route.

The before projection must equal the directive's requested projection. The
after projection is independently validated as current because creating the
directive receipt itself changes the System graph hash. Both frames must remain
on the expected canonical editing revision unless the governed command declares
and reports a revision transition.

## Video-production integration

Storyboard scenes may optionally define a `spatial_layout` with normalized
regions whose purposes are `authentic_reference`, `readable_text`,
`safe_motion`, `caption_safe`, `cta`, or `protected`. Authentic-reference
regions require a source asset ID. A region can be preserved, animated, avoided,
or replaced. This gives the Director and generation adapters a shared mechanical
contract for repository screenshots, titles, captions, motion, and safe areas.

The intended production loop is:

1. SAG Video declares and captures its own verified UI state.
2. The Director binds authentic repository screenshots to storyboard regions.
3. Image or video generators receive exact region and preservation constraints.
4. Downloaded assets are observed and inserted through canonical media and
   timeline commands.
5. Render and review observations identify spatial failures such as unreadable
   text, unsafe crop, occluded CTA, or broken authenticity.
6. Those findings refine the next storyboard or generation pass without
   invalidating unrelated locked scenes.

This makes SAG Video a recursive calibration vessel: it is the subject, the
editor, the observer, and the source of evidence, while authority remains
separated at every transition.

## Implemented surface

- FastAPI declare/current/get/resolve/observe endpoints.
- Runtime event definitions for frame declaration, binding reconciliation,
  action routing, and effect observation.
- Same-origin authenticated Next proxies and typed client methods.
- MCP current-frame and region-resolution tools plus frame-bound directives.
- Studio DOM self-declaration, adaptive grid overlay, semantic action ACK, and
  accessible region list.
- Director storyboard spatial-layout editing and generation-prompt propagation.
- Contract, safety, prompt, TypeScript, mobile, and reconnect test coverage.

## Next additive slices

- Bind imported repository screenshots to `authentic_reference` regions from
  the asset picker and show their hashes in storyboard review.
- Add deterministic text and safe-area observers to rendered scene acceptance.
- Add optional redacted Gemini binding behind the existing feature gate and
  compare its proposals with DOM truth before allowing any actuator route.
- Aggregate observation receipts into per-layout calibration metrics without
  retaining pixels, prompts, or unrestricted provider output.
- Extend the same frame protocol to the render review surface, then to other
  NLKE applications only after SAG Video acceptance evidence is reproducible.

Public release, publication, credentials, provider connections, approvals, and
destructive edits remain human or canonical-command-only. No spatial observer
can cross those gates.
