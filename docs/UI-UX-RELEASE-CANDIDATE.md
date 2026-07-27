# SAG Video UI/UX Release Candidate Plan

## Release intent

Reach a stable personal-dogfood release where SAG Video can take an authentic repository or source, direct the production, preserve evidence, review candidates, build a timeline, render deterministically, and expose a verified artifact without requiring database or API intervention.

This is a preservation-first polish pass. It does not change the information architecture, route names, workflow vocabulary, or SAG's approval boundaries.

## Design read

SAG is a technical video-production cockpit for a solo expert operator. Its established language is dark broadcast control, cyan interaction emphasis, semantic status colors, precise mono data, compact spacing, and low-motion feedback.

- Redesign mode: targeted evolution
- Design system: existing SAG native CSS tokens, informed by Carbon and Fluent operational patterns
- Design variance: 4/10
- Motion intensity: 2/10
- Visual density: 8/10
- Primary surface: responsive web Studio
- Primary dogfood viewport: Android portrait
- Secondary viewport: desktop production workstation

## Current-state audit

### Preserve

- Edit, Context, and System depth switch
- Repository and Source Video workflow switch
- Director stages: Direction, Brief, Prompts, Storyboard, Queue
- Cyan interaction accent and semantic live, success, and warning colors
- One dark theme across the production surface
- 8px radius system, hairline borders, and compact panel rhythm
- 44px mobile control targets
- Explicit human approval for evidence and candidate decisions
- Receipt, revision, hash, and independent-observer language

### Retire or correct

- Missing self-hosted font requests and licensed-font placeholders
- Full Studio reconciliation every 2.5 seconds while the runtime event stream is healthy
- Low-contrast 7px and 8px metadata on mobile
- Context graph nodes that auto-fit too small to read on portrait screens
- Generic project and sequence names such as `test`
- Silent errors, raw validation payloads, and any recurrence of `[object Object]`
- Ambiguous busy states where a command appears idle while work continues
- Browser-only success claims that are not backed by an engine receipt and QC report

### Already closed in this pass

- Removed requests for four absent font files and selected honest platform font stacks
- Reduced full Studio polling to a 15-second reconciliation interval while live events are connected, with a 2.5-second disconnected fallback
- Added readable structured validation errors
- Added the screenshot contact-sheet review and explicit approve/reject decisions
- Produced an authentic 30-second 9:16 SAG proof video with an independent observed-success receipt
- Added revision-checked project and sequence naming directly in Studio
- Added connected, reconnecting, offline, render-in-progress, failure, and verified runtime states
- Added same-origin verified MP4 and JSON receipt downloads in Deliver and Governance
- Bound all Studio data routes to the sequence selected in the page URL
- Verified that the accepted Studio download reproduces the receipt SHA-256 and that failed-QC downloads return HTTP 409

### Current checkpoint

RC0's implementation slice is complete and verified locally. The dogfood control
project is `SAG Repository Proof`; its active sequence is `SAG Repository Short
9x16`. The accepted output remains revision 13 while the descriptive rename is
revision 14, so the UI correctly presents the historical verified revision
without claiming that a newer render exists.

The RC0 exit gate remains open until the same naming-to-download path is repeated
by hand in a clean browser session. RC1 through RC4 also remain open; in
particular, mobile screenshots, keyboard/accessibility evidence, Linux
Playwright execution, and deployed production smoke evidence are not yet
complete.

## Stable-release critical path

The release path must work from the interface with no manual API calls:

1. Create or select a clearly named project and sequence.
2. Choose Repository or Source Video.
3. Complete Direction with inline field validation.
4. Inspect the source and show model-routing rationale.
5. Review and edit the generated brief and prompt modules.
6. Review storyboard scenes and evidence boundaries.
7. Capture or ingest authentic screenshots.
8. Approve or reject each screenshot or visual candidate.
9. Insert only approved, non-stale assets into the timeline.
10. Render the pinned project revision.
11. Show render progress, receipt transition, QC checks, and output hash.
12. Download the verified artifact and receipt.

Any step that still requires curl, direct database access, or manual record repair is a release blocker.

## Work plan

### RC0: Trust and operability

- Rotate any credentials that appeared in earlier screenshots and verify they are absent from repository history and managed captures.
- Give the dogfood project and sequence descriptive names.
- Keep the ChatGPT visual bridge behind `SAG_CHATGPT_VISUAL_BRIDGE` until its OAuth and upload isolation suite passes.
- Add one visible runtime-health state with connected, reconnecting, and offline behavior.
- Ensure every mutating action has disabled, pending, success, and recoverable error states.
- Preserve form input after a recoverable error or stale-revision retry.
- Add direct verified artifact and receipt download actions after observed success.

Exit gate: one clean-session run completes the full critical path without developer tools.

### RC1: Mobile production ergonomics

- Keep the current navigation and workflow labels.
- Reduce header height by grouping secondary commands under a compact overflow action on portrait screens.
- Keep Render visually primary and never hide it behind overflow.
- Raise essential mobile metadata to a 10px minimum and verify WCAG AA contrast.
- Make the Context graph open as a dedicated full-screen inspection surface on portrait screens.
- Add graph fit, reset, and selected-node focus controls. Do not auto-fit below a readable node-label scale.
- Keep the tree as the accessible fallback and preserve focus when switching between tree and graph.
- Validate safe-area insets, browser chrome resize, keyboard-open layouts, and 360px width.

Exit gate: the full critical path is usable at 360x800 and 412x915 with no page-level horizontal overflow and no target smaller than 44px for primary touch actions.

### RC2: Review and timeline clarity

- Make review counts explicit: pending, approved, rejected, and stale.
- Keep candidate alternatives and aspect-family variants visually linked.
- Show why insertion is blocked and provide the exact next action.
- Distinguish selected, approved, active-on-timeline, and stale states without relying on color alone.
- Keep screenshot hashes and provenance available through disclosure instead of permanently occupying mobile space.
- Add a timeline empty state that points to the approved-candidate workflow.
- Verify overlay ordering, crop mode, duration, transform, opacity, and safe-region changes are visible before render.

Exit gate: a new operator can identify what is approved, what can be inserted, and why a candidate is blocked without reading documentation.

### RC3: Accessibility and consistency

- Run a visible-string audit for labels, placeholders, errors, empty states, and confirmations.
- Remove ambiguous icon-only actions or add accessible names and tooltips.
- Verify keyboard order, focus restoration after panels close, Escape behavior, and no focus traps.
- Test 200 percent zoom and reduced motion.
- Validate body, secondary text, form labels, placeholders, and focus rings against WCAG AA.
- Keep red, green, and cyan signals paired with text or icons.
- Standardize loading feedback around the existing mechanical motion language. No decorative perpetual motion.

Exit gate: automated accessibility checks pass, then the critical path passes with keyboard only on desktop.

### RC4: Performance and release evidence

- Measure Studio request volume with runtime connected and disconnected.
- Confirm no font, image, API, or source-map 404s in a production build.
- Keep INP below 200ms and CLS below 0.1 on the primary Studio route.
- Lazy-load the 3D graph and keep it disabled by default on portrait mobile.
- Run Playwright at 1440x900, 768x1024, 412x915, and 360x800.
- Capture screenshots for Direction, Prompts, Review, Context tree, Context graph, timeline, render progress, and verified output.
- Store the accepted artifact hash, receipt, QC report, test results, and known issues in the release evidence directory.

Exit gate: the release evidence can independently prove the build, critical path, and rendered output.

## Acceptance matrix

| Area | Required evidence | Release threshold |
| --- | --- | --- |
| Direction | Playwright form flow | Valid state persists; invalid state is readable and recoverable |
| Model cascade | Routing view plus unit tests | Sol, Terra, and Luna roles are explicit; fallback is deterministic |
| Screenshots | Contact sheet plus decisions | Authentic captures are reviewable; rejected items cannot insert |
| Context | Tree and graph captures | Selected entity remains identifiable at desktop and mobile |
| Timeline | Overlay render test | Still duration, crop, order, and safe area match the frozen revision |
| Render | Receipt and QC report | `observed_success`; every blocking check passes |
| Artifact | FFprobe and SHA-256 | 1080x1920, 30 fps, H.264, AAC, 30 seconds, exact receipt hash |
| Resilience | Disconnect and stale-revision tests | Recovery does not lose user input or duplicate commands |
| Accessibility | Automated scan plus keyboard pass | No critical violations; complete desktop keyboard path |
| Deployment | Production smoke test | Migrations, storage, OAuth boundaries, and feature flags are valid |

## Release boundary

### Ship in the stable release

- Repository-to-video and source-video workflows
- Sol, Terra, and Luna orchestration with explicit routing and receipts
- Authentic screenshot capture, review, decision, and timeline insertion
- Managed still-image intake and deterministic FFmpeg rendering
- Independent artifact observation and QC
- Verified artifact and receipt download
- Responsive Edit, Context, and System surfaces

### Defer until after the stable exit point

- Public ChatGPT app distribution
- NLKE-SAG browser extension or plugin work
- Automated publishing
- Pixel-identical character continuity claims
- Browser automation of ChatGPT image generation
- Additional visual effects that do not improve production clarity or proof

## Definition of the stable exit point

SAG Video is at the stable exit point when:

- the complete critical path passes in a clean environment on mobile and desktop;
- all RC0 through RC4 exit gates pass;
- the accepted proof video and receipt are reproducible from pinned inputs;
- no known issue can corrupt a project, bypass approval, expose credentials, or misrepresent generated content as factual evidence;
- remaining issues are documented polish items with workarounds;
- the release is tagged from a clean, reviewed commit and deployed behind the intended production configuration.

At that point, brainstorming the NLKE-SAG Chrome extension and plugin layer is safe because the host product has a stable interaction contract to extend.
