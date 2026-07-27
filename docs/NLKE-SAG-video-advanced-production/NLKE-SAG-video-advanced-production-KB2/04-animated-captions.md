# Word-Level Animated Caption Composition

## Why word-level timing is the foundation
The entire category of "karaoke captions," bounce/pop effects, glow/pulse, and typewriter reveals depends on one prerequisite: **word-level (not sentence-level) timestamps** from the transcription step. Without per-word start/end times, only static sentence-block subtitles are possible — animated per-word effects are simply not achievable [web:178].

## Caption animation styles (documented taxonomy)
From a production caption tool's feature set, four broad animation families cover essentially all common short-form caption styles [web:178]:
- **Karaoke Highlight**: words light up / color-sweep in sync with speech timing — classic lyric-video style, works well for music and emphasis-driven talking content.
- **Bounce & Pop**: words bounce in with spring physics, pop for emphasis — suited to energetic/comedic content.
- **Glow & Pulse**: neon glow around text, pulse effect on the currently-spoken word — suited to night/club/gaming aesthetics.
- **Typewriter & Reveal**: characters appear one-by-one, or text reveals from left/right/center — suited to dramatic reveals.

## Technical implementation pattern
- Enable **word-level timing** during transcription (Whisper supports this natively — see KB #1 doc 05 on `whisper-node`/`node-whisper`, both of which return arrays with word-level start/end timestamps) [web:178][web:117].
- Rendering uses the **Web Animations API** (or equivalent declarative animation timeline in a native renderer) to create smooth, performant per-word animations synced to the word timing array — critical because naive per-frame re-render of caption state is expensive; declarative animation timelines let the browser/GPU handle interpolation [web:178].
- Workflow: transcribe with word timing → for each word, compute an animation keyframe window `[wordStart, wordEnd]` → apply the selected animation style's keyframe template to that word within its window → composite all words into the caption track.

## Why muted-video captions matter for scoring
85% of social video is watched on mute, making animated/burned-in captions not a cosmetic nicety but a core requirement for any clip's hook and retention performance to register at all [web:178] — this should be treated as a default-on feature in NLKE-SAG's pipeline, not an optional add-on.

## Open-source component for the caption UI layer
- **`geonhwiii/react-karaoke-text`**: a React + TypeScript component library explicitly inspired by Apple Music's karaoke-text animations, built with Vite — directly reusable as the front-end animated-caption rendering component for word-level highlight effects in a TS-based editor [web:179].

## Rendering caption burn-in in the render pipeline
- For final export, captions generated as a timed word-array can be burned in via two paths depending on the rendering engine chosen in KB #1:
  - **Remotion**: render captions as a React component consuming the word-timing array directly inside a `<Composition>`, giving full control over animation via CSS/Framer-Motion-style keyframes synced to `useCurrentFrame()`.
  - **ffmpeg-based pipelines (Editly/ffmpeg.wasm)**: pre-render caption animation to an alpha-channel overlay (e.g., via a headless browser/Canvas render pass) or use `ass`/`ssa` subtitle format, which supports basic per-character/word styling and timing natively via FFmpeg's `subtitles` filter — a lower-fidelity but simpler fallback if not using Remotion.

## Recommendation for NLKE-SAG
Make word-level timestamp extraction (via `whisper-node`/`node-whisper`) a mandatory first step in the pipeline whenever any caption feature is used, standardize on a small set of caption "templates" (karaoke, bounce, glow, typewriter) implemented as parameterized Remotion components (or a fork/extension of `react-karaoke-text`), and treat animated captions as a default rather than opt-in feature given the muted-viewing statistic.
