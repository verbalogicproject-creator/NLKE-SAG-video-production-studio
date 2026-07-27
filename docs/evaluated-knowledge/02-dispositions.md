# Architecture dispositions

## Adopt

- FastAPI is the authoritative API and schema surface.
- The normalized transactional database owns projects, immutable revisions, receipts, jobs, production sessions, and editorial records.
- Native FFmpeg plus ASS or engine overlays is the canonical renderer.
- One master timeline owns media truth; aspect-ratio variants store revisioned overlays and report stale overrides.
- Explainable Clip Quality Score uses fixed versioned weights: Hook 30%, Flow 25%, Value 20%, Delivery 10%, Visual Evidence 10%, Boundary Quality 5%.
- Immutable job inputs, outbox dispatch, leases, cancellation, recovery, and receipts remain the reliability contract. Redis is not a deduplication authority.
- Direct, provider-neutral adapters and downloadable verified exports end the current milestone.

## Pilot

- MediaPipe dominant-face tracking with normalized coordinates, confidence, smoothing, and centered/manual fallback.
- pyannote diarization and diarization-to-face association for multi-speaker content.
- Motion and cursor saliency for screen recordings and action/B-roll.
- Workspace and repository media retrieval for non-destructive B-roll candidates.

## Reference

- Remotion, Editly, browser canvas editors, and competitor workflows inform UX and test fixtures only.
- Stock and generation providers inform the adapter boundary, not the canonical asset or evidence model.

## Defer

- Browser rendering, ffmpeg.wasm production exports, stock-provider search, performance-based score calibration, and analytics feedback loops.
- OAuth credentials, scheduled publication, and public platform delivery.

## Reject

- An uncalibrated “Virality Score” or any promise of reach.
- Remotion, Redis, a browser renderer, or a publisher as a second authority.
- Generated or stock media as proof of a factual repository or source-video claim.
- Silent cost estimates when price is unknown.
- Fixed browser memory ceilings or competitor-internal claims treated as product facts.
