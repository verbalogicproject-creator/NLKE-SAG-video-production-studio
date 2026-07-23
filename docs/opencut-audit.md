# OpenCut integration audit

Audited July 22, 2026.

## Commits

- Current rewrite: `OpenCut-app/OpenCut@5e0696bc9b921dcbaf2f42bdf3e96891a30c1e9e`
- Archived classic editor: `OpenCut-app/opencut-classic@cf5e79e919144200294fb9fed22a222592a0aeea`

Both repositories publish the relevant source under the MIT license. No
OpenCut source or assets are copied into this repository at this stage.

## Result

The current rewrite contains the application shell and UI primitives but no
timeline/editor implementation. Its README lists the Editor API, plugin
architecture, MCP, headless mode, and scripting as future work. It therefore
fails all four integration criteria.

Classic contains a capable editor, but its project loading, IndexedDB/OPFS
storage, renderer, selection, command history, timeline controllers, and WASM
media-time types are coordinated through the internal `EditorCore`. Making a
remote canonical SAG project authoritative would require invasive changes
across those systems, not a bounded adapter.

The proof therefore takes the plan's specified fallback: a thin timeline and
preview backed only by the SAG Video API. This prevents browser state from
becoming a second source of truth. OpenCut can be reassessed when its public
Editor API has stable hydration, event, selection, and command boundaries.

## Reassessment contract

An OpenCut adapter may replace the thin GUI only when a pinned release can:

1. Hydrate an externally supplied canonical project without adopting its
   persistence format.
2. Preserve externally assigned stable item IDs.
3. Emit gestures as typed commands without first mutating private state.
4. Reconcile a newer server revision and surface conflicts.

