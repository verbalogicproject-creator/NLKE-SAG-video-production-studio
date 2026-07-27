# Benchmark Methodology & Target-Device Matrices

## Why this matters
An AI-assisted video pipeline with an offline-capable component (per KB #1's architecture) needs to perform acceptably across a wide range of hardware — from high-end desktop GPUs to mid-range Android phones running Termux/local inference (directly relevant given the user's own stated mobile LLM deployment expertise). Without a defined benchmark methodology and target-device matrix, "does it run fast enough" remains a subjective, untested assumption until users complain.

## What a benchmark methodology needs to define
Based on general software performance-testing practice applied to this domain (no OpusClip-class competitor publishes its internal benchmark methodology publicly, so this section synthesizes standard practice rather than citing a directly-applicable competitor source):
1. **Representative workload set**: a fixed suite of test videos spanning the content types identified in doc 02/03 (talking-head, multi-speaker podcast, screen recording, B-roll-heavy) at multiple resolutions/durations, so performance numbers are comparable across hardware and over time as the codebase changes.
2. **Metrics to capture per pipeline stage** (aligning with the stages defined across both knowledge bases):
   - Transcription (Whisper) — real-time factor (audio duration ÷ processing time).
   - Face/subject tracking + diarization — frames-per-second processed.
   - Reframing/crop-trajectory computation — time per output aspect ratio.
   - Caption rendering — time to composite word-level animations.
   - Final render (Remotion/Editly/ffmpeg.wasm) — time per output minute, at each target resolution.
   - End-to-end pipeline latency — from upload to first scored clip candidate, and from approval to published output.
3. **Resource consumption metrics**: peak memory usage (critical given ffmpeg.wasm's documented ~500MB in-browser ceiling from KB #1 doc 02), CPU/GPU utilization, battery impact (for mobile/on-device scenarios).

## Target-device matrix (tiering approach)
Given the offline-capability requirement and the user's expertise in mobile LLM deployment, a target-device matrix should define **hardware tiers** rather than testing every possible device, e.g.:
- **Tier 1 — High-end desktop/workstation**: dedicated GPU (for Remotion Lambda-equivalent local rendering, or local Veo-adjacent inference if any component runs on-device), representing the power-user/prosumer creator segment.
- **Tier 2 — Mid-range laptop (CPU-only or integrated GPU)**: the most common "creator on a laptop" scenario — this is the tier ffmpeg.wasm's browser-based architecture (KB #1 doc 02) is realistically targeting, and where the "under 30 seconds for a 1-minute clip" benchmark cited in that research applies.
- **Tier 3 — High-end mobile (flagship Android/iOS)**: relevant given the user's Termux/Android local-LLM background — represents on-device inference feasibility for lighter pipeline stages (e.g., word-level transcription via a mobile-optimized Whisper variant) even if full rendering still happens server-side.
- **Tier 4 — Mid/low-range mobile**: defines the floor of acceptable degraded experience (e.g., fallback to server-side processing entirely, or reduced feature set like skipping local face-tracking preview).

## Benchmark validation approach (borrowed from the hook-scoring research methodology)
The hook-retention-scoring study reviewed in doc 01 offers a transferable methodology pattern worth adapting for performance benchmarking too: it cross-validated its predictive model against **real, externally-verifiable ground truth** (actual YouTube/TikTok retention curves) rather than relying purely on internal/synthetic test metrics, reporting explicit statistical fit (r²=0.74 overall, r²=0.81 within the short-form cohort) [web:136]. Applied to performance benchmarking: don't just measure synthetic "time to render a test video" — track real production job latencies and resource consumption in aggregate across the actual device/hardware mix of real users, and periodically validate that synthetic benchmark suite results still correlate with real-world production performance distributions.

## Note on source coverage
No OpusClip-class competitor, nor any of the open-source projects reviewed across both knowledge bases (Remotion, Editly, OpenCutAI, etc.), publishes a public target-device matrix or formal benchmark methodology document. This is consistent with the general industry pattern of treating internal performance-engineering practices as non-public. This document is therefore a **synthesized recommendation based on general software performance-engineering practice** adapted to this project's specific stack and offline/mobile requirements, not a sourced summary of an existing published methodology. Treat this as a starting framework to formalize internally, and consider it a priority area for dedicated internal engineering documentation once the pipeline architecture (per KB #1 and the rest of this KB) stabilizes.

## Recommendation for NLKE-SAG
Define a fixed benchmark video suite (4-6 videos spanning talking-head, multi-speaker, screen-recording, and B-roll-heavy content, at 1080p and 4K) and a 4-tier device matrix (desktop/GPU, mid-range laptop, flagship mobile, low-end mobile) before your first public beta. Instrument every pipeline stage (per the metrics list above) to log latency and peak memory in production from day one, not just in synthetic pre-launch testing, so real-world performance data can validate or correct the synthetic benchmark suite over time — mirroring the ground-truth-validation approach used successfully in the hook-scoring research.
