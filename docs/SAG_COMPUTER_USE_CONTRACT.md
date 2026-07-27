# SAG Computer-Use Contract v1

`sag-computer-use/1.0` is the reusable boundary between a user-activated browser tab, a model, and SAG's canonical command service. It is not a general browser automation API.

## Authority model

- Pairing issues a workspace-scoped `browser_extension` principal with audience `computer_use` and only `computer_use:observe`, `computer_use:act`, `computer_use:capture`, and `computer_use:attach`.
- The user activates the current HTTP(S) tab with one explicit gesture. Activation ends on navigation, origin change, tab close, pause, or the eight-hour activity expiry.
- Any activated HTTP(S) tab may publish a bounded metadata observation. It receives no actions unless its exact origin matches an installed, versioned, Ed25519-signed profile.
- v1 executes only `read` and `safe_reversible` profile actions. Reversible actions declare a compensation action. Costed, destructive, approval-only, credential-admin, and ineligible actions are rejected.
- Canonical SAG actions still pass through the registry, revision check, workspace check, and canonical receipt machinery. The extension has no direct database authority.

The browser principal is audience-isolated: it cannot call project, render, delivery, publication, or ordinary command endpoints. The MCP surface exposes activity/action inspection, intent creation/execution, and receipt readback; it does not expose an approval bypass.

## Observation and evidence

Routine observations contain hashes, normalized rectangles, stable semantic bindings, visibility, a bounded viewport declaration, and optional SAG context references. Generic observation does not read input values or arbitrary page text. It never persists a raw frame.

Screenshots are explicit checkpoints. The extension calls `captureVisibleTab` only after the user clicks a checkpoint or confirms an action whose signed policy is `before_after_required`. Bytes go directly to the scoped multipart endpoint—not through JSON and not through a remote URL. SAG accepts PNG, JPEG, or static WebP up to 32 MiB, 8192 pixels per side, and 40 megapixels; it verifies the decoded format, normalizes orientation/color, strips metadata, stores canonical PNG bytes, and records original/canonical SHA-256 hashes. Checkpoints expire after 30 days unless attached to governed context.

An effect receipt binds the signed profile, intent, before/after observation hashes, predicates, checkpoint lineage, compensation action, and any underlying canonical receipt. Browser-visible verification is explicitly marked `same_extension_adapter`; it is evidence, not an independent oracle.

## Signed origin profiles

Profiles use `sag-computer-use-profile/1.0`, exact HTTP(S) origins, semantic locators, JSON argument schemas, action routing, effect predicates, safety class, and checkpoint policy. SAG verifies the canonical JSON body with an allowlisted Ed25519 public key and rejects conflicting versions or rollback.

Two development profiles are included:

- `services/sag-engine/profiles/sag-studio-local.v1.json` enables `timeline.set_clip_transform` on local SAG Studio.
- `services/sag-engine/profiles/generic-fixture-local.v1.json` enables a reversible input change on the local fixture.

Generate a deployment profile with exact production origins, keep its private key outside the repository, and sign it with:

```sh
python scripts/sign-computer-use-profile.py profile.json --private-key-file /secure/path/ed25519-private-key.txt
```

Configure trusted public keys as base64url-encoded raw Ed25519 keys:

```sh
SAG_COMPUTER_USE_TRUSTED_KEYS='{"production-key-1":"BASE64URL_PUBLIC_KEY"}'
```

Unsigned profiles are accepted only when `SAG_COMPUTER_USE_DEV_PROFILES=1`; never enable that setting in a shared deployment.

## Local use

1. Set `SAG_COMPUTER_USE_V1=1` for the engine and start SAG normally.
2. Build the unpacked Manifest V3 extension with `pnpm --filter @verbalogix/nlke-sag-extension build`.
3. Load `apps/nlke-sag-extension/dist` through Chrome's **Load unpacked** developer action.
4. In Studio, click **Pair browser**. Open the extension overlay on the intended tab, enter the engine origin and one-time code, then click **Activate this tab**.
5. On a selected video/image clip, **Confirm clip scale → 0.85** captures the before checkpoint, creates and consumes a one-use intent, executes the canonical revision-checked edit, refreshes Studio, captures the after checkpoint, and records the effect receipt. **Compensate clip scale → 1.00** exercises the declared recovery path.

The fixture can be served with any static server on `http://localhost:4173` after installing its signed profile through `POST /api/computer-use/profiles`.

## HTTP lifecycle

The canonical endpoints are under `/api/computer-use`: profile install/list; activity create/get/list/pause; observation create; eligible action list; intent create/execute; execution completion; checkpoint multipart upload; context attachment; and receipt readback. `/api/contract` publishes the exact Pydantic schemas and current feature state.

No v1 interface accepts screen coordinates, arbitrary JavaScript, background tab traversal, arbitrary download URLs, credential material, or publication authority.

## Acceptance gate

The release acceptance is one local Studio activity that records an explicit before checkpoint, executes `timeline.set_clip_transform` with `scale: 0.85` against an exact project revision, observes the incremented revision and changed state, records an explicit after checkpoint and successful effect receipt, then executes the compensation back to `scale: 1.00`. Tests also cover signature failure, one-use ticket replay, token audience isolation, generic observation with zero actions, navigation invalidation, workspace isolation, and image intake bounds.
