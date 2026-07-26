# SAG Video dogfood pause gates

Status: approved implementation gates, July 26, 2026

The production plan pauses at complete, testable creator outcomes. A pause is
not a demo checkpoint or a reason to add more features. Normal feature work
stops while the current slice is used on real projects, friction is recorded,
and only blockers, regressions, or misleading behavior are corrected.

## Gate discipline

Every gate must provide:

- one valuable end-to-end job through normal GUI controls;
- truthful empty, loading, failure, retry, stale, and success states;
- phone access for ordinary creator operations;
- preserved project, sequence, selection, revision, and receipt context;
- inspectable evidence, prompt, provider, observation, and artifact identity;
- an acceptance fixture and a written dogfood outcome;
- no control that implies an unavailable capability.

At the start of a pause, freeze the implementation in a commit and record its
test evidence. Use at least two focused sessions. Classify findings as blocker,
workflow friction, quality limitation, or later enhancement. Resume planned
feature work only after the gate has an explicit proceed, revise, or stop
decision.

## Pause 0: connected production control surface

State: ready for immediate manual dogfood.

Use the existing SAG Video project without requesting a new paid generation.
Exercise Director, Prompting Studio, Storyboard, Queue, Edit, Context, System,
spatial map, verified Media, and Governance from the phone.

Exit evidence:

- context and selection survive projection changes and reload;
- the five Director tabs remain contained and keyboard/touch operable;
- prompt consumers, resolved hashes, observations, and receipts are
  understandable;
- page-level horizontal drift is absent;
- every confusing hierarchy or dead-end transition is recorded.

This gate evaluates the unified context shell and information architecture. It
does not claim a complete creator workflow.

## Pause 1: approved production packet

State: next build target.

Produce a provider-ready package without spending generation quota:

- frozen, redacted repository evidence;
- reviewed prompt revision and creative brief;
- reviewed storyboard and scene routing;
- imported authentic repository screenshots with hashes;
- spatial preserve, readable-text, safe-motion, caption, CTA, and protected
  regions;
- cost estimate and human-approved storyboard receipt.

Dogfood with SAG Video and one structurally different repository. The exit
question is whether the owner trusts the package enough to authorize provider
spending.

## Pause 2: cost-controlled scene laboratory

State: planned after Pause 1 acceptance.

Add image-first scene candidates, image review, image-to-video routing,
per-scene accept/reject, selective video generation, selective regeneration,
provider cost/quota reporting, and idempotent observed timeline insertion.

Use the second SAG Video short as the acceptance production. Exit requires that
expensive video generation happens only after composition review, rejected
scenes can be replaced independently, retries do not duplicate charges or
timeline items, and every asset links back to its prompt, scene, provider
operation, and observation.

## Pause 3: finishable short

State: planned after the scene laboratory is stable.

Complete a watchable export without leaving Studio. Required surfaces include
real audio waveforms, narration/music/native-audio lanes, gain, fades, ducking,
loudness, timed captions, safe-area review, scene trim/split/replace/reorder,
platform reframing, deterministic titles/end cards, and full render
verification.

Produce three complete shorts, including one from a non-SAG repository, using
normal GUI operations. This is the general creator-product gate.

## Pause 4: recursive calibration loop

State: planned after finishing is dogfoodable.

Bind factuality, continuity, readability, crop, motion, audio, and caption
observations to the exact prompt and scene revisions that produced them. Compare
accepted and rejected attempts, propose bounded refinements, require human
acceptance, and selectively regenerate only affected unlocked work.

Exit requires repeated correction cycles to reduce the same observed failure
without rewriting failed history as success. This gate validates the central
NLKE-SAG thesis rather than only the editor.

## Pause 5: private release operation

State: planned after calibration evidence.

Exercise full artifact review, scene decisions, claim/evidence checklist, cost
confirmation, artifact-hash-bound human approval, private or unlisted delivery,
ambiguous publication recovery, publication receipt, and post-publication
verification. Public promotion is not required and remains separately approved.

## Approved implementation order

1. Pause now for connected-control-surface dogfood.
2. Build only what is required for the approved production packet.
3. Pause before provider spending.
4. Build the image-first selective scene laboratory.
5. Produce and review the second SAG Video acceptance short.
6. Build professional finishing and complete three creator runs.
7. Add recursive calibration after the underlying creator workflow is stable.
8. Validate private release before considering broader admission.

Spatial awareness and Prompting Studio are transversal layers in these gates,
not parallel products. The same canonical engine, revisions, commands,
observations, receipts, and human authority remain the integration boundary.
