# Speaker, Face, and Subject Tracking

## Why this matters
Reframing horizontal footage to vertical only looks professional if the crop follows the actual subject — the person talking, the moving action, or the salient object — rather than a static center crop that clips faces or loses context.

## Core detection techniques by content type
Different source content needs different tracking signals, and a good system exposes all of them as configuration options rather than hardcoding one approach [web:156]:
- **Talking head**: face detection performs best.
- **Screen recordings**: cursor position and saliency tracking (not face detection) — since there may be no visible face at all.
- **Multi-speaker (podcasts/interviews/panels)**: speaker-switching reframing, cutting between active speakers based on audio diarization.
- **B-roll/action footage**: motion-based saliency, following the most active region of the frame.

## Speaker diarization
- **Definition**: identifying and separating distinct speakers within an audio track — "who said what and when" — which is the foundational signal for multi-speaker reframing and speaker-switching cuts [web:157].
- **Open-source model**: `pyannote` (pyannote-audio) is the de facto standard diarization library used by open-source AI editing projects, e.g., OpenCutAI uses it for auto-detecting who's talking and auto-cutting at speaker boundaries [web:159].
- Pairing pattern: diarization output (speaker timeline) + face detection (visual speaker localization) lets the system determine which face on screen corresponds to the currently active audio speaker, enabling automatic camera cuts between speakers in multi-person video without manual keyframing [web:156][web:161].

## Active speaker detection & reframing architecture (3-stage pipeline)
A well-documented pattern from OpusClip's public API docs, broadly applicable [web:156]:
1. **Subject detection**: run face detection or motion saliency per frame (or frame group) to identify the dominant subject's bounding box.
2. **Temporal smoothing**: raw frame-by-frame tracking jitters; apply a smoothing pass (splines or low-pass/EMA/Kalman filtering) on the bounding-box center to produce camera-like movement (slow pans, holds, smooth tracks) instead of jittery jump-cuts.
3. **Crop and re-render**: render output at the target aspect ratio with the crop window centered on the smoothed subject path.

## Common pitfalls (documented failure modes)
- **Defaulting to face tracking on non-face content** — screen recordings need saliency tracking, animation needs explicit region tracking, music videos with hard cuts need cut-aware tracking; matching tracking mode to content type is essential, not optional [web:156].
- **Trusting auto-detection on multi-subject scenes** — two people on opposite sides of frame confuse simple face trackers; systems should either let users designate which subject to follow, or use speaker-switching mode driven by diarization [web:156].
- Screen-recording-specific handling: detect Zoom/Loom sources automatically, switch to saliency tracking, but preserve the "bubble cam" (webcam overlay) as a corner overlay while cropping out UI chrome — a specific, non-obvious edge case worth designing for explicitly [web:156].

## Open-source implementations to study/reuse
- **OpenCutAI** (`ekaanth/opencut` fork with AI suite layered on top): fully local-first, no-cloud video editor stack combining Whisper (transcription), XTTS v2 (voice cloning), Stable Diffusion (image gen), Llama 3.2 via Ollama (natural language commands), **Pyannote** (speaker diarization), and **MediaPipe** (face detection) — auto-detects speakers and auto-cuts at speaker boundaries, plus face-tracking auto-reframe to 9:16 [web:159]. This is the closest fully-open-source reference architecture for exactly what NLKE-SAG needs, and everything runs via a single `docker compose up -d`.
- **`FujiwaraChoki/supoclip`**: documented face detection & cropping system transforming landscape/square video to vertical 9:16 using a multi-stage pipeline (detailed technical writeup available via DeepWiki) [web:163].
- **`SuhatAkbulak/yolo-actor-reframe-engine`**: demonstrates YOLO-based object detection + tracking for computing a moving crop window, with EMA/Kalman filtering applied to the crop trajectory for smooth motion before rescaling to 9:16 output — a concrete open-source implementation of the smoothing technique described above [web:165].
- **`KazKozDev/auto-vertical-reframe`**: "scene-aware" vertical auto-reframe CLI explicitly designed to avoid losing the subject when converting horizontal footage to 9:16 [web:169].
- Face detection + OpenCV combo pattern (MediaPipe for landmarks, OpenCV for frame manipulation) is repeatedly cited across independent hobbyist rebuilds of clipping tools as the practical, low-cost starting stack before reaching for anything heavier [web:168].

## Recommendation for NLKE-SAG
Adopt the **MediaPipe (face) + Pyannote (diarization) + YOLO or motion-saliency (non-face content) + EMA/Kalman smoothing** stack as the core tracking engine — all open-source, all capable of running fully offline/on-device, directly matching the project's offline requirement. Expose tracking mode as an explicit per-job configuration (face / saliency / speaker-switching / explicit-region) rather than a single auto-detect-only mode, since content-type mismatches are the most commonly cited failure mode across every source reviewed.
