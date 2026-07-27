# Source register

| Subject | Primary source | Version evaluated | License / terms | Accessed | Confidence | Disposition |
|---|---|---:|---|---|---|---|
| FastAPI | https://github.com/fastapi/fastapi | 0.136.3 upstream; repository requires 0.115+ | MIT | 2026-07-27 | High | Adopt |
| FFmpeg | https://ffmpeg.org/documentation.html and https://ffmpeg.org/legal.html | Runtime-pinned system build; record `ffmpeg -version` in export provenance | LGPL/GPL depends on build configuration | 2026-07-27 | High | Adopt |
| MediaPipe | https://github.com/google-ai-edge/mediapipe | 0.10.35 upstream; optional adapter | Apache-2.0 | 2026-07-27 | High | Pilot |
| pyannote.audio | https://github.com/pyannote/pyannote-audio | 4.0.4 upstream; optional adapter | MIT for code; model terms evaluated separately | 2026-07-27 | High | Pilot |
| CycloneDX | https://cyclonedx.org/specification/overview/ | Specification 1.7 | Specification and tooling terms are source-specific | 2026-07-27 | High | Adopt |
| Cloud Tasks | https://cloud.google.com/tasks/docs | Managed service contract, not a library version | Google Cloud service terms | 2026-07-27 | High | Adopt |
| Remotion | https://github.com/remotion-dev/remotion | Not pinned | Company license applies to some use; verify before adoption | 2026-07-27 | Medium | Reference |
| ffmpeg.wasm | https://github.com/ffmpegwasm/ffmpeg.wasm | Not pinned | MIT wrapper; bundled FFmpeg licensing still applies | 2026-07-27 | Medium | Defer |

“Upstream” records are evidence, not automatic dependency upgrades. Repository lockfiles and container digests remain the deployed versions. Unknown or model-specific licenses stay unknown until reviewed; they are never inferred from the adapter's code license.
