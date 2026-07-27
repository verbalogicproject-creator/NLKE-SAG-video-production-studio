# AI Video Generation & Render-as-a-Service APIs

## Google Veo on Vertex AI (TypeScript)
- **SDK**: `@microfox/veo-on-vertex-ai` — a TypeScript SDK for the Veo API on Google Cloud Vertex AI [web:56].
- **Install**: `npm install @microfox/veo-on-vertex-ai` [web:56].
- **Required env vars**: `GOOGLE_CLOUD_PROJECT` (project ID), `GOOGLE_CLOUD_LOCATION` (regional endpoint, e.g. `us-central1`) [web:56].
- **API surface**: `VeoonVertexAIAPISdk` constructor to init client; `createVeoonVertexAIAPISDK`, `generateVideo`, `fetchOperationStatus`, `pollOperation` functions — Veo generation is async/operation-based, requiring polling for completion [web:56].
- **Additional community guides**: dev.to and Japanese technical blog (Qiita) walkthroughs cover implementing production-level Veo integration directly in TypeScript, useful supplementary reference material for the exact request/response shapes and error handling patterns [web:54][web:53].
- **Relevance to NLKE-SAG**: Since the project already combines Omni + Veo, this SDK (or a custom thin wrapper following the same pattern) is the most direct TypeScript-native way to call Veo without going through Python, keeping the whole pipeline in one language.

## Video Generation / Render APIs (template-driven, non-generative-AI)
These are **traditional programmatic rendering services** — good for deterministic assembly of AI-generated raw footage into a finished branded video (titles, overlays, transitions) via API rather than local rendering:

### Shotstack
- Provides an official **TypeScript SDK**: `shotstack/shotstack-sdk-typescript` on GitHub [web:95].
- Cloud-based video editing API — JSON "Edit" schema describing tracks/clips, submitted via API, rendered server-side.

### Creatomate
- REST API for generating videos/images/GIFs from templates or raw "RenderScript" JSON, callable from Node.js, PHP, Ruby, Python, etc. [web:99].
- **Endpoint**: `POST https://api.creatomate.com/v2/renders` with `template_id`, `modifications` (dict of field→new value, e.g., swapping in an AI-generated background video URL or dynamic caption text), optional `render_scale`, `max_width`/`max_height`, `webhook_url` for async completion callback [web:98].
- **Workflow fit**: Design a branded template once in Creatomate's visual editor, then programmatically inject AI-generated video/text per social post — good for producing on-brand content at scale without hand-building compositions each time [web:96][web:99].

### Comparison: Local (Remotion/Editly/ffmpeg.wasm) vs Cloud (Shotstack/Creatomate)
| Approach | Pros | Cons |
|---|---|---|
| Local render (Remotion, Editly, ffmpeg.wasm) | Free, offline-capable, full control, no per-render cost | Requires local compute; scaling needs your own infra (or Remotion Lambda) |
| Cloud render API (Shotstack, Creatomate) | No infra to manage, webhook-driven async workflow, fast to prototype templates | Per-render cost, requires internet, less control over exact FFmpeg internals |

Given the user's stated goal of **offline-capable** editing plus AI integration, local rendering (Remotion/Editly/ffmpeg.wasm) should be the primary path, with a cloud API as an optional scale-out fallback for heavy batch jobs.
