# Proxy/Original Synchronization

## The problem
High-resolution source footage (4K/8K, high bitrate) is too heavy to scrub, preview, and edit interactively in real time — especially in a browser or on mobile. Professional NLE workflows solve this with **proxy media**: lightweight, lower-resolution transcodes used during editing, which are swapped back to the original full-resolution source only at final render/export time.

## Why this is a distinct engineering problem (not just "make a smaller file")
The core challenge is **keeping every edit decision (cuts, crops, reframing trajectories, caption timing, effects) expressed in a resolution- and timebase-independent way**, so that:
1. All interactive editing happens against the proxy (fast to decode, fast to seek, low bandwidth for browser/mobile delivery).
2. The final render substitutes the original full-resolution/full-bitrate media at export time using the same edit decisions (frame-accurate timecodes, not pixel-based crop coordinates that don't scale).
3. Any AI analysis (tracking, scoring, transcription) that is expensive to run at full resolution can run once on the proxy and have its results (bounding boxes, timestamps) rescaled/reapplied to the original at render time — avoiding redundant expensive processing on full-res source.

## Architectural implications for NLKE-SAG's stack
Given the tools already covered in KB #1:
- **Editly/Remotion compositions** should store crop/track/caption data as **normalized coordinates (0.0-1.0) and timecodes**, not absolute pixel positions tied to a specific resolution — this is what makes proxy-to-original swaps possible without re-running detection.
- **ffmpeg-based proxy generation**: a low-resolution, low-bitrate H.264 proxy (e.g., 480p or 720p) can be generated on ingest via a single ffmpeg transcode pass, stored alongside the original, and referenced during interactive editing/preview (Etro canvas compositing or ffmpeg.wasm-based browser preview) while final Remotion/Editly renders reference the full-resolution original.
- **AI analysis on proxy, application on original**: run face-tracking, scoring, and transcription against the proxy for speed, then store all resulting timestamps/bounding boxes in resolution-independent form so the final render pipeline can reapply them to the original at full fidelity — critical for keeping render costs and turnaround time manageable at scale.

## Note on source coverage
This specific "proxy/original synchronization" pattern is a well-established professional NLE concept (used in DaVinci Resolve, Premiere, Final Cut Pro) but was not covered in dedicated public documentation from the OpusClip-class tools researched for this knowledge base — none of the reviewed competitor blogs or open-source projects explicitly documented their proxy-handling architecture. This is a genuine architectural gap that NLKE-SAG will likely need to design from first principles, informed by standard NLE proxy-workflow conventions rather than by an existing open-source reference implementation. Treat this document as directional guidance rather than a sourced deep-dive, and prioritize further first-party research (e.g., studying LosslessCut's or Remotion's internal handling of resolution-independent edit decision lists) if this becomes a near-term build priority.
