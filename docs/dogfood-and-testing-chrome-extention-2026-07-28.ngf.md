---
id: dogfood-and-testing-chrome-extention-2026-07-28
kind: dogfood_acceptance_protocol
format: ngf/0.0.1
audience:
  - Eyal Nof
  - OpenAI Codex
  - Claude
  - Gemini
status: deferred-awaiting-human-dogfood
owner_area: nlke-sag-computer-use
title: NLKE-SAG Chrome extension dogfood and testing gate
written: 2026-07-28
written_by:
  - OpenAI Codex
depends_on:
  - docs/SAG_COMPUTER_USE_CONTRACT.md
  - docs/progress/SAG_COMPUTER_USE_V1_2026-07-27.md
  - docs/research/NLKE_SAG_CHROME_EXTENSION_CAPABILITY_INTERSECTIONS.md
baseline_commit: 1a1bf47857023c941337f68217a9f0c97ec11ae3
parallel_next_work:
  - Sol/Terra/Luna delegation harness
last_verified: not-yet-dogfooded
---

# NLKE-SAG Chrome extension dogfood and testing gate

This is the parked human dogfood protocol and future outcome receipt for the
first real desktop-Chromium run of SAG Computer-Use v1. Dogfood is deliberately
deferred while Sol/Terra/Luna delegation work proceeds.

Planning, implementing, and testing the delegation harness against deterministic
fixtures and dry-run contracts may continue now. Live model-driven browser
actuation remains disabled until this protocol is eventually completed; a model
cascade must not be used to hide an unreliable browser contract.

Do not place a pairing token, cookie, API key, environment-file contents,
screenshot bytes, private signing key, or captured form value in this document.
Record opaque IDs, bounded findings, hashes, and safe artifact paths only.

## Intended acceptance loop

```text
human activates the current tab
  -> extension records bounded metadata
  -> exact origin resolves a signed profile
  -> human confirms an explicit before checkpoint and safe edit
  -> SAG executes against the exact project revision
  -> Studio refreshes and the extension records the after state
  -> effect receipt binds observations, checkpoints, profile, and canonical receipt
  -> human runs the declared compensation
  -> a second receipt proves recovery
```

## Locked v1 boundary

- Desktop Chrome/Chromium is the acceptance target. Android extension support
  is not assumed or claimed.
- One toolbar gesture activates only the current HTTP(S) tab.
- Navigation, origin change, pause, tab close, or expiry ends authority.
- Unsigned/unprofiled origins are observation-only and expose zero actions.
- Only packaged semantic handlers or canonical SAG commands may execute.
- No coordinate clicking, arbitrary JavaScript, unrestricted CDP, silent
  capture, continuous screenshots, background browsing, credentials,
  approvals, delivery, or publication.
- Screenshots occur only after an explicit checkpoint click or a confirmed
  action whose signed policy requires before/after checkpoints.
- Same-extension effect observation is evidence with the declared
  `same_extension_adapter` limitation; it is not independent proof.

## Preconditions

Fill these without exposing secrets:

| Field | Value |
| --- | --- |
| Dogfood date/time | `PENDING` |
| Tester | `PENDING` |
| OS | `PENDING` |
| Browser and exact version | `PENDING` |
| Extension ID | `PENDING` |
| Repository commit | `1a1bf47857023c941337f68217a9f0c97ec11ae3` |
| Studio origin | `PENDING` |
| SAG engine origin | `PENDING` |
| Workspace ID | `PENDING` |
| Project ID | `PENDING` |
| Initial project revision | `PENDING` |
| Selected visual item ID | `PENDING` |

Required state:

- [ ] The repository is at the recorded commit or a newer explicitly recorded commit.
- [ ] `SAG_COMPUTER_USE_V1=1` is configured without printing the environment.
- [ ] SAG Engine and Studio are healthy.
- [ ] Studio is opened at exactly `http://localhost:3000` or
  `http://127.0.0.1:3000` for the bundled local signed profile. A different
  origin requires a separately signed exact-origin deployment profile.
- [ ] A project contains at least one video or image clip that can be selected.
- [ ] Browser DevTools has no copied tokens or sensitive request bodies.
- [ ] A safe scratch project or recoverable project revision is being used.

## Build and load

Build from the Ubuntu proot used by this repository:

```sh
proot-distro login ubuntu -- bash -lc 'cd /data/data/com.termux/files/home/openai/sag-video && corepack pnpm --filter @verbalogix/nlke-sag-extension typecheck && corepack pnpm --filter @verbalogix/nlke-sag-extension build'
```

Then, in desktop Chrome/Chromium:

1. Open the extensions manager.
2. Enable developer mode.
3. Choose **Load unpacked**.
4. Select `apps/nlke-sag-extension/dist`.
5. Pin **NLKE-SAG Computer Use** to the toolbar.
6. Inspect its declared permissions before continuing.

Expected install-time permissions:

- `activeTab`
- `scripting`
- `storage`
- optional HTTP(S) host access, requested only for the exact SAG engine origin
  entered during pairing

Record:

| Check | Result | Evidence / finding |
| --- | --- | --- |
| Extension loads without manifest error | `PENDING` | |
| Service worker starts without exception | `PENDING` | |
| Overlay opens and closes from toolbar | `PENDING` | |
| No unexpected install-time host warning | `PENDING` | |
| Exact engine-origin permission is requested during pairing | `PENDING` | |

## Test matrix

Use `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN`. Every P0 row must pass.

| ID | Priority | Scenario | Expected result | Outcome | Evidence / notes |
| --- | --- | --- | --- | --- | --- |
| CU-01 | P0 | Studio **Pair browser** | UI displays a ten-minute workspace-scoped browser pairing code | `PENDING` | |
| CU-02 | P0 | Enter code in overlay once | Pair succeeds with `browser_extension` / `computer_use`; code cannot be reused | `PENDING` | |
| CU-03 | P0 | Activate Studio tab | Activity becomes active; signed `sag.studio.local` profile and version are visible | `PENDING` | |
| CU-04 | P0 | Observe Studio | Bounded bindings and hashes are recorded; no raw routine screenshot or input value is retained | `PENDING` | |
| CU-05 | P0 | Activate an unprofiled HTTP(S) page | Generic metadata observation works and available actions are exactly empty | `PENDING` | |
| CU-06 | P0 | Navigate the activated generic page | Old activity pauses/invalidates; an action or observation requires a new activation | `PENDING` | |
| CU-07 | P0 | Select a video/image clip in Studio | Overlay resolves `studio.timeline.selected_clip` and its stable item identity | `PENDING` | |
| CU-08 | P0 | Confirm scale to `0.85` | Before checkpoint occurs visibly; exact-revision canonical edit commits; Studio refreshes | `PENDING` | |
| CU-09 | P0 | Verify scale effect | Item scale is `0.85`; project revision increments exactly once | `PENDING` | |
| CU-10 | P0 | Inspect effect receipt | Status is `observed_success`; profile hash/version, observation hashes, both checkpoint IDs, underlying receipt ID, and failure-domain disclosure exist | `PENDING` | |
| CU-11 | P0 | Download both checkpoint artifacts | Both return canonical PNG; downloaded SHA-256 values match their checkpoint records | `PENDING` | |
| CU-12 | P0 | Confirm compensation to `1.00` | A second before/action/after cycle restores scale and creates a successful recovery receipt | `PENDING` | |
| CU-13 | P0 | Reuse or replay an execution | Already-consumed intent/ticket is rejected and causes no extra revision | `PENDING` | |
| CU-14 | P0 | Press **Pause and release tab** | Browser state releases immediately; later action attempts require reactivation | `PENDING` | |
| CU-15 | P0 | Use computer-use bearer against a normal project/render route | Request is denied for audience mismatch | `PENDING` | Do not record token |
| CU-16 | P1 | Close an active tab | Extension releases local activity; server activity is paused or safely expires | `PENDING` | |
| CU-17 | P1 | Stop engine during pause or navigation | Browser authority still releases locally; reconnect does not silently resume it | `PENDING` | |
| CU-18 | P1 | Restart extension service worker/browser | No stale active action authority returns; new pairing/activation behavior is explicit | `PENDING` | |
| CU-19 | P1 | Trigger action with no eligible selected clip | Clear bounded error; no screenshot/action/revision side effect beyond explicitly begun evidence | `PENDING` | |
| CU-20 | P1 | Open overlay at narrow and wide desktop widths | Controls remain readable, keyboard reachable, and do not block required page controls | `PENDING` | |

## Primary acceptance run record

### Activation

| Record | Value |
| --- | --- |
| Activity ID | `PENDING` |
| Origin | `PENDING` |
| Profile ID/version | `PENDING` |
| Profile SHA-256 | `PENDING` |
| Initial observation ID/hash | `PENDING` |

### Scale `0.85`

| Record | Value |
| --- | --- |
| Before observation ID/hash | `PENDING` |
| Before checkpoint ID/hash | `PENDING` |
| Intent ID | `PENDING` |
| Execution ID | `PENDING` |
| Underlying canonical receipt ID | `PENDING` |
| After observation ID/hash | `PENDING` |
| After checkpoint ID/hash | `PENDING` |
| Effect receipt ID/hash/status | `PENDING` |
| Revision before → after | `PENDING` |
| Visible result | `PENDING` |

### Compensation to `1.00`

| Record | Value |
| --- | --- |
| Compensation intent ID | `PENDING` |
| Compensation execution ID | `PENDING` |
| Compensation canonical receipt ID | `PENDING` |
| Compensation effect receipt ID/hash/status | `PENDING` |
| Revision before → after | `PENDING` |
| Visible recovered result | `PENDING` |

## Privacy and safety audit

- [ ] No screenshot occurred merely from opening, pairing, activating, or observing.
- [ ] Each screenshot had a contemporaneous visible human gesture or confirmed
  before/after action policy.
- [ ] Generic observations contain no input/textarea value and no arbitrary page text.
- [ ] Screenshot bytes were uploaded as multipart bytes, never embedded in MCP/JSON.
- [ ] No arbitrary URL was supplied for SAG to fetch.
- [ ] No token or credential appears in overlay output, receipts, logs, this file, or screenshots.
- [ ] A profile mismatch produced observation-only behavior.
- [ ] The extension requested no debugger, downloads, native messaging, clipboard,
  tab-capture, desktop-capture, or persistent all-sites authority.
- [ ] The two receipts identify `same_extension_adapter` rather than claiming
  independent visual verification.
- [ ] Rejected/failed attempts remained failures and were not promoted as success.

## UX observations

Record concrete behavior, not general impressions.

| Area | Finding | Severity | Proposed correction |
| --- | --- | --- | --- |
| Pairing comprehension | `PENDING` | | |
| Active/paused state clarity | `PENDING` | | |
| Screenshot consent clarity | `PENDING` | | |
| Action/compensation wording | `PENDING` | | |
| Receipt readability | `PENDING` | | |
| Error recovery | `PENDING` | | |
| Keyboard accessibility | `PENDING` | | |
| Overlay obstruction | `PENDING` | | |
| Perceived latency | `PENDING` | | |

## Repetition and stability

Complete three consecutive clean cycles on a recoverable project. Do not count
a cycle that reused old observation/checkpoint/receipt IDs.

| Cycle | Pair/activate | Scale `0.85` | Receipt | Compensate `1.00` | Receipt | Final revision/item state |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `PENDING` | |
| 2 | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `PENDING` | |
| 3 | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `PENDING` | |

## Defect log

| ID | Severity | Reproduction | Expected | Actual | Evidence IDs | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `NONE-YET` | | | | | | |

Severity:

- P0: authority escape, credential exposure, silent capture, irreversible or
  cross-workspace action, false successful receipt, or corrupted canonical state.
- P1: core pairing/action/checkpoint/compensation path cannot complete reliably.
- P2: recoverable UX, performance, or evidence-quality defect.
- P3: cosmetic issue with no contract/evidence impact.

Stop immediately on any P0. Revoke the pairing, preserve only safe IDs/hashes,
and do not proceed to model delegation.

## Optional proof-to-video observation

This is not a v1 automated capability claim. If useful, manually attach the
approved dogfood checkpoints to a scratch SAG project and judge whether they
could anchor a generated/authentic composite rather than another screenshot
slideshow.

| Question | Finding |
| --- | --- |
| Do the checkpoints clearly prove the actual Studio state? | `PENDING` |
| Which authentic region must remain ungenerated? | `PENDING` |
| What generated motion/background could improve production value safely? | `PENDING` |
| Are the images sufficient to prompt a product-faithful generated scene? | `PENDING` |
| What additional semantic event markers would improve future editing? | `PENDING` |

## Exit decision before live model-driven browser actuation

Allowed final status values:

- `accepted-for-model-delegation`
- `needs-fix-and-repeat`
- `blocked-environment`
- `rejected-contract-unsafe`

The delegation harness may be built and tested before this run. It may advance
to live browser actuation only when:

- [ ] Every P0 test passes.
- [ ] Three consecutive scale-and-compensation cycles pass.
- [ ] No unresolved P0 or P1 defect remains.
- [ ] Generic origins expose zero actions.
- [ ] Navigation and pause reliably revoke authority.
- [ ] Before/after checkpoint consent is unmistakable.
- [ ] Effect and compensation receipts are complete and truthful.
- [ ] No sensitive value appears in retained evidence.
- [ ] The tester understands what the extension can observe and what it can act on.
- [ ] The exact accepted commit and browser version are recorded.

| Final field | Value |
| --- | --- |
| Final status | `PENDING` |
| Accepted/rejected by | `PENDING` |
| Decision time | `PENDING` |
| Accepted commit | `PENDING` |
| Blocking defects | `PENDING` |
| Recommended next change | `PENDING` |

## Post-dogfood handoff

When this document reaches `accepted-for-model-delegation`, update its front
matter and commit the completed receipt. Until then, model work should use
fixtures, recorded contracts, or dry-run execution. The delegation design adds
these roles above the browser contract:

```text
Sol: plan and resolve intent
Terra: execute only an issued, profile-eligible action
Luna: summarize bounded observations and audit receipts economically
```

No model receives broader browser authority merely because the manual dogfood
passed.
