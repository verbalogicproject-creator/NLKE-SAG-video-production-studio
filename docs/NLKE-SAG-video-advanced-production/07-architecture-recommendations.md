# Architecture Recommendations for NLKE-SAG-video-advanced-production

## Design goals recap
1. TypeScript-first, AI-integrated (Omni + Veo models) content pipeline.
2. Offline-capable advanced video editing/production (not just AI generation).
3. Path to revenue: content-creator tooling + SaaS marketplace (multi-tenant publishing).

## Proposed layered stack

### Layer 1 — AI Generation
- **Veo**: `@microfox/veo-on-vertex-ai` TS SDK for text/image-to-video generation, operation-based (poll for completion) [web:56].
- **Omni model(s)**: existing integration (per user's own stack) for multimodal reasoning/prompting — orchestrates what to generate, storyboard breakdowns, and captions/text overlays.
- **Speech/captions**: `whisper-node` or `node-whisper` for fully local, offline transcription and word-level timestamps of any voiceover/dialogue [web:117][web:119].

### Layer 2 — Editing & Composition Engine (the "offline advanced video editing" core)
- **Primary engine**: Remotion — code-driven, type-safe compositions; renders locally via `npx remotion render`, no dependency on any cloud API once ffmpeg + node modules are installed [web:13].
- **Reference UI architecture**: fork/study `designcombo/react-video-editor` for the multi-track timeline UI pattern (already React+TS+Remotion, CapCut/Canva-like) rather than building the editor UI from zero [web:49][web:59].
- **Real-time browser preview layer**: Etro for canvas-based live compositing while the user scrubs/edits, decoupled from the heavier Remotion final-render pass [web:46].
- **Fully offline in-browser fallback / mobile**: ffmpeg.wasm for trims, format conversion, social-preset exports when no server/render farm is available — run inside a Web Worker per the architecture pattern in doc 02 [web:11][web:19].
- **Automated batch assembly**: Editly for headless, JSON-config-driven stitching of AI-generated clips + titles + music, ideal for an LLM agent that outputs an Editly spec directly [web:29][web:34].
- **Auto dead-space removal**: shell out to `auto-editor` (Python CLI callable via Node `child_process`) as a pre-pass on any raw/voiceover footage, with FCPXML export enabling manual polish in DaVinci Resolve if needed [web:122][web:116].

### Layer 3 — Manual/Pro Editing Bridge (optional power-user path)
- LosslessCut for fast, lossless manual trims and its HTTP automation API for scripted desktop workflows [web:67][web:69].
- FCPXML/Premiere export from auto-editor or Remotion project state for round-tripping into professional NLEs when a creator wants full manual control [web:122].

### Layer 4 — Distribution / SaaS Marketplace
- **Ayrshare** as primary multi-platform publisher, using `profileKey` per end-user/tenant for the marketplace model, and `setTwitterByo()` for X compliance [web:90].
- **PostEverywhere** as a secondary candidate given its explicit AI-agent/MCP orientation — could reduce the orchestration code needed if the pipeline is driven by an LLM agent end-to-end [web:71][web:78].
- **Cloud render fallback**: Creatomate/Shotstack for on-brand templated renders at scale if local compute becomes a bottleneck for high creator volume [web:98][web:95].

## Suggested pipeline flow
1. Omni model plans content (script, shot list, captions) → 2. Veo generates raw video segments → 3. Whisper transcribes any voice/dialogue for captions → 4. auto-editor removes dead air from raw segments (optional) → 5. Editly or Remotion assembles final composition (titles, captions, transitions, branding) driven by a JSON/TS spec the AI agent generates → 6. ffmpeg.wasm (or local ffmpeg via Remotion) exports platform-specific presets (9:16 TikTok/Reels, 16:9 YouTube, 1:1 feed) → 7. Ayrshare/PostEverywhere publishes to connected creator accounts on schedule → 8. Loop analytics back into the Omni model for iterative content optimization.

## Key technical risks to track
- ffmpeg.wasm's lack of HEVC support and ~500MB in-browser memory ceiling may force a native/server fallback for longer or 4K source footage [web:11].
- Veo generation is asynchronous (operation polling), so the pipeline orchestration layer needs a job-queue/webhook pattern, not synchronous calls [web:56].
- X/Twitter's BYO-key requirement (since March 2026) adds a per-tenant onboarding step for the SaaS marketplace if X support is offered [web:90].
- Licensing: Etro (GPL-3.0) and LosslessCut (GPL-2.0) are copyleft — factor this into any closed-source SaaS packaging decisions [web:52][web:75].
