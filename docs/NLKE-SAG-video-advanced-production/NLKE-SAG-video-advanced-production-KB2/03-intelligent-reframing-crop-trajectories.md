# Intelligent Reframing & Crop Trajectories

## The core problem
Converting 16:9 landscape footage to 9:16 (or 1:1, 4:5) for social platforms via a static center crop or letterbox loses 30-50% of usable screen area on vertical platforms and frequently clips the actual subject [web:156].

## Reframing pipeline stages (recap + technical detail)
Building on the tracking pipeline in doc 02, the reframing-specific technical details are:
1. **Detection** produces a raw per-frame bounding box of the subject (face, motion blob, or explicit region).
2. **Temporal smoothing** — this is the step that separates amateur auto-crop tools from professional-feeling output. Raw bounding-box centers are noisy frame to frame; a smoothing filter (moving average / EMA / Kalman filter / spline fit) is applied to the *trajectory* of the crop-window center over time, producing slow pans and holds that resemble intentional cinematography rather than jittery tracking [web:156][web:165].
3. **Crop-and-render**: the final output is rendered at the target aspect ratio with the crop window following the smoothed path, not the raw noisy path [web:156][web:165].

## Multi-aspect-ratio-from-one-source pattern
- A single source video should typically produce 9:16, 1:1, 4:5, and 16:9 outputs from **one submission/one API call**, each with independently configurable captions, durations, and overlays — not separate manual re-edits per platform [web:156].
- This "submit once, render many" pattern is the standard architecture in production reframing APIs and should be a first-class concept in NLKE-SAG's job model (one source asset → N output renditions, each with its own crop trajectory if content differs per aspect ratio).

## Content-type-aware tracking mode selection
As detailed in doc 02, the same reframing engine must branch its detection strategy based on content type — this is worth restating here as a reframing-specific design requirement:
- Talking head → face detection.
- Screen recording (Zoom/Loom) → motion/cursor saliency, with special-cased UI-chrome cropping and webcam-bubble preservation as an overlay [web:156].
- Multi-speaker → diarization-driven speaker-switching cuts, or grid/split-screen layouts when multiple people must remain visible simultaneously [web:158][web:161].
- B-roll/action → motion saliency following the most active region [web:156].

## Split-screen / grid layouts for multi-person content
When cutting between speakers isn't desirable (e.g., a reaction needs both people visible), an alternative to speaker-switching is a **grid/split-screen layout** — laying two or three people out cleanly in a vertical frame rather than cramming them into a single crop strip [web:158][web:161]. This should be an explicit selectable output mode, not just a fallback.

## Practical implementation reference (YOLO + Kalman)
The `yolo-actor-reframe-engine` project demonstrates the concrete technical steps end-to-end [web:165]:
1. Run YOLO object/person detection per frame to get a bounding box.
2. Recalculate the crop region each frame based on the detected object's center coordinates (not a static crop).
3. Apply EMA or Kalman filtering across the sequence of bounding-box centers to eliminate frame-to-frame jitter.
4. Rescale the final cropped frames to the target 9:16 (or other) output resolution.

This is a fully open-source, inspectable implementation of the exact pipeline OpusClip-class products use, and is a strong starting point or reference for an in-house build.

## Recommendation for NLKE-SAG
Implement reframing as a distinct pipeline stage that takes (a) the source video, (b) a tracking-mode selection (or auto-detected content-type classification), and (c) a list of target aspect ratios, and outputs N independently-smoothed crop trajectories rendered in a single batch job. Use Kalman filtering (not simple frame-averaging) for trajectory smoothing since it handles both smoothing and prediction (useful when the subject briefly leaves frame). Treat split-screen/grid layout as a first-class alternative output mode alongside single-subject tracking, selectable per multi-speaker job.
