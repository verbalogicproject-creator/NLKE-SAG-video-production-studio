# NLKE–SAG Chrome Extension: capability-intersection research

Research date: July 27, 2026

## Executive conclusion

The strongest product is not another general browser agent. It is a **Verified Browser Operations Studio**:

> Activate SAG on the current tab, perform or delegate a governed workflow, capture only meaningful visual checkpoints, prove the resulting state, and turn the evidence package into a reproducible incident, SOP, QA artifact, or authentic SAG video.

Claude in Chrome, Bardeen, Axiom, HARPA, Scribe, Percy, and Loom cover portions of this workflow. In the reviewed product material, none claims the complete intersection of signed exact-origin semantic profiles, model-independent before/after state, reversible actions with declared compensation, effect receipts bound to hashes, explicit rather than continuous screenshots, and direct governed video production.

## Phase 1 — Capability inventory

Latency values are engineering estimates, not Chrome guarantees. Chrome's [extension API index](https://developer.chrome.com/docs/extensions/reference/api) and [Manifest V3 guidance](https://developer.chrome.com/docs/extensions/develop/migrate/what-is-mv3) are the primary platform references.

| Category | Capability / API | Input → output | Typical latency | Constraints | Contract status |
| --- | --- | --- | ---: | --- | --- |
| Activation | `chrome.action`, `activeTab` | toolbar gesture → temporary current-tab access | <100 ms | Access is gesture-bound; SAG deliberately expires it on navigation/origin change | Green |
| Activation | `chrome.commands` | shortcut → command/current tab | <100 ms | Shortcut conflicts; only a few suggested shortcuts | Green |
| Activation | `chrome.contextMenus` | user selection/link/image → click event | <100 ms | Needs new evidence-intent types | Amber |
| UI | `chrome.sidePanel` | gesture/tab → persistent extension page | 20–200 ms | Chrome 114+; opening programmatically requires a user interaction | Green shell |
| UI | content script + Shadow DOM | packaged bundle → in-page control surface | 10–100 ms | Page messages are untrusted; UI can be visually obstructed | Green/current |
| Observation | DOM/accessibility semantics | active document → bounded roles/bindings/rectangles | 1–100 ms | Never collect field values by default | Green/current |
| Observation | `MutationObserver` | subtree changes → debounced metadata deltas | 1–50 ms/event | Noise/CPU risk on dynamic pages | Green while active |
| Lifecycle | `webNavigation`, tab events | document lifecycle → activation revocation | event-driven | SPA/document identity needs care | Green |
| Actuation | packaged semantic handlers | signed action + validated args → DOM event/effect | 10–500 ms | MV3 prohibits downloaded executable adapters | Green/current |
| Actuation | `chrome.scripting` | packaged file/function → execution result | 10–150 ms | Needs `scripting` plus `activeTab`/host access | Green/current |
| Actuation | registered content scripts | packaged adapter + exact matches → persistent registration | 10–100 ms | Handler code must still ship with the extension | Future optimization |
| Actuation | `chrome.userScripts` | user code → page execution | 10–200 ms | Requires special user toggle; violates no-arbitrary-JS boundary | Red |
| Tab control | `chrome.tabs` | query/create/update/group → tab state | 10–200 ms | Broad multi-tab autonomy is outside v1 | Amber/Red by action |
| Screenshot | `tabs.captureVisibleTab` | explicit active-window request → PNG/JPEG data URL | 50–500 ms | At most two calls/second; may capture sensitive browser pages | Green, explicit only |
| Archive | `pageCapture` | tab → MHTML | 0.2–2 s | Excessive sensitive retention | Red/unneeded |
| Media | `chrome.tabCapture` | visible user invocation → tab `MediaStream` | 0.1–1 s setup | Local audio playback stops unless routed back through `AudioContext` | Amber amendment |
| Media | `desktopCapture.chooseDesktopMedia` | Chrome chooser → one-use stream ID | user-dependent | Always user-selected; audio varies by source/OS | Amber amendment |
| Processing | `chrome.offscreen` | packaged hidden document → DOM/media/blob work | 50–300 ms | One document per profile; only runtime API directly exposed | High-value Green support |
| Privacy | offscreen canvas / packaged WASM | pixels + redaction regions → sanitized bytes/hash | 20–500 ms | Redact before upload; packaged code only | Green |
| Messaging | `runtime.sendMessage`, `Port` | validated JSON → inter-context result | <10–100 ms | Privileged worker must validate all page-originated messages | Green/required |
| Runtime | MV3 service worker | events → short-lived execution | wake 10–300 ms | Usually stops after 30 seconds idle; globals disappear | Green with stored state |
| Scheduling | `chrome.alarms` | time/period → wake event | seconds/minutes | May notify for reactivation; background browsing remains excluded | Amber |
| State | `storage.session` | bounded JSON → ephemeral activity state | 1–30 ms | 10 MiB; not persisted to disk | Green/current |
| State | `storage.local` / `sync` | JSON → durable/synced preferences | 1–100 ms | Do not sync receipts, screenshots, or secrets | Green for settings |
| Enterprise | `storage.managed` | admin policy → read-only config | 1–50 ms | Extension must enforce schema/policy | Amber/later |
| Permissions | `chrome.permissions` | user gesture + optional origin/API → grant | user-dependent | Request capability-by-capability | Green/current |
| Identity | `identity.launchWebAuthFlow` | OAuth URL → redirect result | 0.5–30 s | SAG one-time pairing is simpler for dogfood | Alternative |
| Downloads | `chrome.downloads` | explicit intake/query → download record/events | network-bound | Can expose local paths/history; scope to visible intake session | Amber amendment |
| Clipboard | offscreen + Clipboard API | explicit text/image request → bytes | 10–200 ms | Highly sensitive; never watch continuously | Amber |
| Network policy | `declarativeNetRequest` | declarative rules → browser enforcement | network path | Powerful but does not require reading traffic | Amber signed-policy amendment |
| Network inspection | `webRequest` / CDP Network | host traffic → request metadata/content | event-driven | Credential, privacy, and prompt-injection exposure | Red for wedge |
| Instrumentation | `chrome.debugger` + CDP | protocol methods → DOM/network/input/runtime data | 5–100 ms/call | Powerful visible debugger attachment; conflicts with v1 restrictions | Red |
| Dev tooling | DevTools panel APIs | inspected window → developer evidence panel | user-dependent | Separate developer-only surface | Amber/later |
| Local bridge | Native Messaging | JSON → installed native host | <5–100 ms | New process/filesystem authority and deployment burden | Amber/major amendment |
| Device facts | system display/CPU/memory/storage | query → diagnostic metadata | 5–100 ms | Some APIs/fields are ChromeOS-specific | Supporting evidence |
| Notification | `chrome.notifications` | receipt/failure → OS alert | 10–500 ms | Best for human-required/completion events | Green |
| Authentication | WebAuthn | challenge → user-authenticated credential | user-dependent | WebAuthentication Proxy is for remote-desktop interception, not approval | Green normal WebAuthn |
| Hardware trust | `enterprise.platformKeys` | managed device key → non-exportable signature | 10 ms–seconds | ChromeOS enterprise only | Hardware-gated later |

Primary constraints: [`activeTab`](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab), [content scripts and messaging](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts), [scripting](https://developer.chrome.com/docs/extensions/reference/api/scripting), [remote-code restrictions](https://developer.chrome.com/docs/extensions/develop/migrate/remote-hosted-code), [tab capture](https://developer.chrome.com/docs/extensions/reference/api/tabCapture), [desktop capture](https://developer.chrome.com/docs/extensions/reference/api/desktopCapture), [offscreen documents](https://developer.chrome.com/docs/extensions/reference/api/offscreen), [service-worker lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle), [storage](https://developer.chrome.com/docs/extensions/reference/api/storage), [optional permissions](https://developer.chrome.com/docs/extensions/reference/api/permissions), [downloads](https://developer.chrome.com/docs/extensions/reference/api/downloads), [declarative network rules](https://developer.chrome.com/docs/extensions/reference/api/declarativeNetRequest), [debugger](https://developer.chrome.com/docs/extensions/reference/api/debugger), and [native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging).

Required physical probes before broad promises: target Chrome version; desktop/Android extension support; tab/system audio per OS; `MediaRecorder` codecs; Chromium-variant differences; native-host installation on Windows/macOS/Linux/Termux; and worker suspension during long uploads/model turns.

## Phase 2 — Obvious features

1. Toolbar or shortcut activation of the current tab.
2. Side panel plus in-page semantic overlay.
3. Explicit screenshot checkpoint.
4. Signed profile exposing safe actions on one origin.
5. Session-only activity state.
6. Receipt/failure notifications.
7. Offscreen local screenshot redaction.
8. Context-menu evidence attachment.
9. Explicit browser-download intake.
10. User-authorized tab audio/video capture.
11. Active-tab mutation/profile-health warning.
12. Enterprise-managed origin/profile/endpoint configuration.
13. Native handoff to local SAG/FFmpeg.
14. DevTools incident evidence panel.

These are useful table stakes, but no one item is the moat.

## Phase 3 — Killer-feature engine

### Cross-category intersections

| Intersection | Emergent product |
| --- | --- |
| Semantic DOM + explicit screenshots + SAG renderer | Authentic proof-to-video, not a screenshot slideshow |
| Signed profiles + reversible actions + effect receipts | Transactional browser automation with auditable undo |
| DOM mutations + profile bindings + repository revision | UI drift sentinel that explains which governed workflow broke |
| Context selection + local redaction + hashing + attachment | Minimum-disclosure evidence capsule |
| Tab A/V + semantic event stream + transcript | Demo automatically cut on real product actions |
| Sol planning + Terra execution + Luna review + receipts | Model-team delegation without shared raw browser authority |
| Accessibility semantics + checkpoint + visual alignment | Functional and visual QA in one reproducible report |
| Download session + MIME/hash intake + candidate governance | Verified artifact inbox for ChatGPT/HF/fal.ai output |
| Incident freeze + compensation + video rendering | Bug reproduction that doubles as an explanatory incident film |

### Continuous-loop test

- Continuous raw screenshots become surveillance: reject.
- Debounced active-tab metadata becomes a UI/profile drift sentinel.
- Continuous binding checks become capture-recipe health monitoring.
- Continuous effect hashes become a state-transition ledger.
- Visible tab capture becomes a semantic screen recorder and needs a separate active-media contract.
- Scheduled checks should notify the user to reactivate, not silently browse.

### Market scan

- [Claude in Chrome](https://support.claude.com/en/articles/12012173-get-started-with-claude-in-chrome) validates demand for a browser-resident agent and exposes broad manual/automatic approval modes, but also demonstrates the resulting permission surface.
- [Bardeen](https://chromewebstore.google.com/detail/bardeen-automate-browser/ihhkmalpkhkoedlmcnilbbhhbhnicjga), [Axiom](https://axiom.ai/automate/chrome/), and [HARPA](https://harpa.ai/welcome) cover cross-app automation, extraction, screenshots, AI prompts, monitoring, and scheduled runs.
- [Scribe](https://scribe.com/lp/chrome-extension) turns captured human workflows into screenshot SOPs.
- [Percy](https://www.browserstack.com/docs/percy/references/percy-browser-extension) captures DOM snapshots and visual diffs for review.
- Computer-use vendors themselves call out unfamiliar UI reliability, confirmation, and prompt injection as central problems; see [OpenAI's CUA overview](https://openai.com/index/computer-using-agent/) and [Claude browser safety guidance](https://support.claude.com/en/articles/12902428-use-claude-in-chrome-safely).

Inference: generic automation, page chat, process capture, and visual diffing are crowded. The defensible intersection is a model-neutral, cryptographically attributable production record.

### Chains of three or more

```text
User activation → signed observation → before checkpoint → safe action
→ effect verification → after checkpoint → receipt → SAG video/QC

Natural-language intent → Sol plan → policy/action resolution → Terra execution
→ effect predicate → receipt → compensation → Luna review

Unexpected state → activity freeze → local redaction → route/profile/hash capture
→ reproduction sequence → project attachment → narrated incident film

Mutation metadata → binding comparison → confidence degradation
→ explicit diagnostic checkpoint → profile-owner notification → signed revision
```

## Phase 4 — Constraint-aware ranking

| Rank | Feature | Impact | Effort | Contract |
| ---: | --- | --- | --- | --- |
| 1 | Verified workflow → authentic SAG video | Very high | Medium | Green |
| 2 | Transactional safe action + undo receipt | Very high | Medium | Green |
| 3 | UI/profile drift sentinel | High | Medium | Green while active |
| 4 | Reproducible incident capsule | High | Low–medium | Green |
| 5 | Local-redacted evidence handoff | High | Low–medium | Green |
| 6 | Sol/Terra/Luna plan-execute-review split | High | Medium | Green |
| 7 | Verified browser-download intake | High | Medium | Amber |
| 8 | Semantic tab recording with real audio | Very high | High | Amber |
| 9 | Visual/accessibility QA flywheel | High | High | Green/Amber |
| 10 | Enterprise managed profile deployment | High later | High | Amber |
| 11 | Native NLKE desktop bridge | Very high later | Very high | Amber |
| 12 | Generic CDP browser agent | Crowded/high risk | Very high | Red |

The highest risks are hostile page content and overbroad authority. Chrome recommends minimizing permissions and using `activeTab`/optional permissions because less access means less data to leak ([privacy guidance](https://developer.chrome.com/docs/extensions/develop/security-privacy/user-privacy)). Page text must remain evidence, never authority; only the worker may invoke privileged APIs; handlers ship as packaged code; each request binds workspace/activity/tab/origin/profile/ticket; captures remain visible and explicit; and same-adapter receipts disclose their verification limitation.

## Phase 5 — Killer-feature cards

### 1. Verified Proof-to-Video

A real governed workflow becomes a polished product video while authentic UI evidence remains distinguishable from generated atmosphere.

**Capability chain:** activation → profile observation → checkpoints → safe action → receipt → storyboard/render
**APIs:** `action`, `scripting`, `captureVisibleTab`, `storage.session`, SAG computer-use/render
**Hardware:** none
**Dependencies:** SAG Engine/renderer
**Models:** Sol narrative plan; Terra bounded execution; Luna economical QC
**Privacy:** only explicit frames leave the browser
**Landscape:** Scribe/Loom capture process; SAG adds semantic receipts and governed media production

### 2. Transactional Browser Actions

Each safe edit has a declared precondition, exact target/action, expected effect, receipt, and compensation path.

**Capability chain:** intent → signed action → pre-state → execution → predicate → receipt → compensation
**APIs:** packaged handler, messaging, SAG one-use tickets
**Hardware:** none
**Dependencies:** installed origin profile
**Models:** planner-agnostic; model is never verifier
**Privacy:** arguments are schema- and origin-bounded
**Landscape:** automation tools log runs; SAG formalizes reversible, effect-verified transactions

### 3. UI Drift Sentinel

While a user-authorized tab is active, deterministic binding checks warn when a release invalidates a capture/action contract before an expensive run fails.

**Capability chain:** mutation → binding health → profile/revision comparison → warning → checkpoint
**APIs:** `MutationObserver`, navigation events, notifications, profile API
**Hardware:** none
**Dependencies:** signed registry, optional repository revision
**Models:** Luna may summarize; matching remains deterministic
**Privacy:** metadata only, no continuous pixels or field values
**Landscape:** Percy finds visual drift; automation finds selector failure; SAG joins both to production impact

### 4. Reproducible Incident Capsule

One gesture freezes a redacted visual checkpoint, route/document identity, profile version, recent governed effects, and note, then attaches or renders the bundle.

**Capability chain:** gesture → freeze → redaction → hash → receipt bundle → incident/video
**APIs:** commands, `captureVisibleTab`, offscreen canvas, context attachment
**Hardware:** none
**Dependencies:** SAG workspace; optional issue adapter
**Models:** cheap summary; stronger model only for hypotheses
**Privacy:** exact capture moment and pre-upload redaction
**Landscape:** replay/debug and SOP tools capture more; SAG creates a bounded governed artifact

### 5. Model-Team Browser Delegation

Sol plans, Terra executes only authorized actions, and Luna compresses/reviews the receipt; cooperation happens through SAG records rather than shared browser power.

**Capability chain:** context → Sol plan → policy compile → Terra action → receipt → Luna review
**APIs:** overlay/side panel, model cascade, tickets, receipt API
**Hardware:** none
**Dependencies:** configured cascade
**Models:** Sol high-value planning; Terra structured execution; Luna cheap repetitive analysis
**Privacy:** role-specific minimum context
**Landscape:** single-agent loops dominate; SAG separates reasoning, authority, actuation, and verification

### 6. Private Evidence Lens

The user selects only the needed region/link/text/image, redacts locally, hashes it, and attaches it without ingesting a whole page or transcript.

**Capability chain:** selection → extraction → redaction → hash → scoped upload → attachment
**APIs:** context menus, DOM, offscreen, SAG intake
**Hardware:** none
**Dependencies:** managed intake
**Models:** optional local OCR/classifier; never authenticity approver
**Privacy:** minimum disclosure by construction
**Landscape:** copilots send page context; SAG makes bounded provenance first-class

### 7. Semantic Screen Recording

Tab audio/video plus semantic action markers lets SAG cut on real state transitions and merge authentic UI with generated visuals and correct narration/music.

**Capability chain:** capture consent → tab A/V → semantic markers → intake → edit/audio → verified render
**APIs:** `tabCapture`, offscreen media, semantic observer, SAG intake
**Hardware:** audio output; microphone only for live narration
**Dependencies:** media contract and renderer
**Models:** Sol story; Terra timing; Luna transcript cleanup
**Privacy:** unmistakable live-capture state and explicit stop
**Landscape:** Loom captures; SAG adds state-aware editing and evidence rules
**Contract amendment:** media authority, audio routing, consent, retention, size

### 8. Verified Artifact Inbox

During an explicit intake session, a ChatGPT/HF/fal.ai download is detected, checked, hashed, and offered as a governed SAG candidate—never silently scraped from conversation URLs.

**Capability chain:** intake session → download → MIME/hash → reservation → candidate → approval
**APIs:** downloads, local file/blob, SAG visual intake
**Hardware:** none
**Dependencies:** supported creation surface
**Models:** optional alignment model; approval stays human
**Privacy:** only session-scoped downloads
**Landscape:** automation can download; SAG supplies lineage, QC, and approval
**Contract amendment:** download/path authority and retention

### 9. Evidence-Aware Accessibility QA

DOM semantics and an explicit visual checkpoint produce functional/visual warnings tied to a reproducible governed workflow.

**Capability chain:** semantics → profile → checkpoint → accessibility/visual checks → receipt
**APIs:** content DOM, checkpoint, SAG alignment
**Hardware:** none
**Dependencies:** QC adapter
**Models:** vision can improve confidence but cannot approve
**Privacy:** bounded semantics, not full DOM
**Landscape:** accessibility scanners and Percy cover separate layers; SAG relates them to real effects

### 10. Enterprise-Signed Browser Operations

Managed policy pins endpoints, origins, keys, profiles, and disabled action classes; supported ChromeOS deployments may add hardware-backed signing.

**Capability chain:** managed policy → signed profile → scoped principal → action → receipt → compliance export
**APIs:** `storage.managed`, enterprise deployment, optional `enterprise.platformKeys`
**Hardware:** managed ChromeOS only for hardware attestation
**Dependencies:** enterprise administration
**Models:** provider-neutral
**Privacy:** policy can prohibit captures, native hosts, origins, or providers
**Landscape:** managed agents offer allowlists; SAG's wedge is attributable action/effect evidence

## Recommended sequence

1. Finish and dogfood the current contract shell.
2. Build Verified Proof-to-Video first.
3. Add local redaction and Incident Capsules.
4. Add active-tab-only UI Drift Sentinel.
5. Connect Sol → Terra → Luna through intents and receipts.
6. Amend separately for download intake.
7. Amend separately for semantic tab recording and real audio.
8. Consider native messaging only after browser-only value is proven.
9. Do not add generic CDP control merely to imitate existing agents.

The moat is not “AI can click Chrome.” It is: **SAG can show what was intended, what was authorized, what actually changed, what evidence proves it, how to undo it, and how to turn that truth into a production artifact.**
