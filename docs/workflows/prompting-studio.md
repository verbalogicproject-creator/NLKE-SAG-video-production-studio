# SAG Video Prompting Studio

Status: integrated first slice, `sag-prompt-studio/0.1`

Prompting Studio is the versioned instruction layer shared by the Director and
repo-to-video pipeline. It does not create another execution engine. It makes
the prompts already flowing through the authoritative engine visible,
editable, comparable, and mechanically bound to their downstream results.

## Pipeline position

```text
repository evidence + human direction
              -> brief and storyboard proposals
              -> editable prompt modules
              -> exact provider compilation
              -> human-approved generation
              -> media observation and timeline insertion
              -> factual, spatial, audio, and render findings
              -> proposed prompt refinement
```

The final arrow is the same recursive SAG feedback loop. Observation identifies
which instruction revision produced an effect. It does not silently rewrite the
instruction or declare the output successful.

## Implemented now

- A persistent `Prompts` tab inside the existing Director panel.
- A real routing topology from direction and planning into scene video, Lyria
  music, Gemini TTS narration, observed assets, and the timeline.
- Editable source modules for creative direction, Omni continuity, Veo
  continuity, music direction, and narration guidance.
- Read-only engine-resolved modules for the selected provider scene, Veo
  exclusions when applicable, and the complete TTS narration script.
- Model registry lifecycle, notes, and capability readback.
- Module content hashes, heuristic token estimates, consumers, dispatch mode,
  warnings, local saved drafts, comparison state, and restore.
- An engine-owned resolved prompt-bundle hash covering aspect ratio, scene model
  routing, all compiled scene prompts, Veo exclusions, music, and narration.
- Generation receipts and idempotency keys bound to that exact hash.
- Responsive single-column workbench, horizontally scrollable module selector,
  44-pixel phone targets, keyboard-native controls, and no WebGL dependency.

## Authority boundaries

- Editing a module changes the current Director proposal and clears local brief
  approval where appropriate.
- Saving a draft stores comparison history in the existing per-project browser
  Director session. It is not a canonical approval.
- Prompt preview is a scoped read operation. It performs no provider call and
  persists no prompt text in runtime events.
- Storyboard generation approval remains a human-bound engine receipt.
- Generation records the resolved prompt revision and requires the existing
  human confirmation.
- Prompting Studio cannot grant commands, bypass evidence checks, insert media,
  approve release, or publish.

## What manual testing should show now

Open Director and choose `Prompts`. Before a brief exists, Creative direction
is editable and the interface truthfully reports that provider modules are not
ready. After brief generation, Omni, Veo, music, and narration-guidance modules
appear. After storyboard generation, selecting a scene shows the exact compiled
provider input and the routing topology activates its video, music, and
narration branches.

Changing an editable module updates its estimated tokens and resolved hashes
after a short debounce. `Save draft` records a local comparison point;
`Restore` returns to the last saved text. The prompt revision shown at the top is
the same hash family bound into a subsequent generation receipt. The resolved
scene and narration inputs are read-only because their sources are the reviewed
brief and storyboard fields.

On a phone, the Director occupies the viewport, the five workflow tabs remain
available, prompt modules become a horizontal selector, the editor becomes one
column, and action targets remain at least 44 pixels high.

Prompting Studio follows the wider unified-shell rule. It is not a destination
page. Opening it preserves the active workspace, project, sequence, evidence,
storyboard, selected scene, revision, and queue. The same rule applies as the
production environment evolves: focused modules use the full phone viewport,
while their relationships remain visible through semantic routing and shared
receipts rather than permanent desktop sidebars.

## Planned additive slices

1. Persist named prompt templates and revisions in the authoritative engine,
   with project, workspace, and reusable-library scopes.
2. Add typed variables and a safe template compiler for evidence anchors, brand
   kit, aspect ratio, scene timing, spatial regions, and reference-asset hashes.
3. Add per-scene prompt overrides with dependency analysis so only affected,
   unlocked scenes become stale.
4. Add a governed natural-language edit module that previews canonical commands
   before execution instead of directly manipulating the UI.
5. Add image-generation and image-to-video prompt modules for the lower-cost
   keyframe-first workflow.
6. Add prompt evaluations for evidence support, text readability, spatial-safe
   areas, continuity, audio balance, and provider-specific prompt anatomy.
7. Link observation receipts back to module revisions and propose refinements;
   require human acceptance before creating a new active revision.
8. Add MCP read/compare/propose tools only after the persistence and approval
   contracts are frozen. MCP will not receive an authority shortcut.

The current implementation is useful for inspecting and refining the real
repo-to-video prompt flow. It is not yet a general prompt-template database, an
automatic optimizer, or a replacement for storyboard and release approval.
