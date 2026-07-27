# Render Conformance: Loudness, True Peak, Safe Areas, Artifact Verification

## Why this matters
Final-render quality control (QC) catches problems before publishing — audio too loud/quiet, clipped peaks, text cropped by platform UI, or encoding artifacts — that would otherwise damage a creator's platform standing (e.g., YouTube/TikTok flagging or demonetizing poorly-encoded content) or simply look unprofessional.

## Loudness normalization: EBU R128
- **EBU R128** is the broadcast-industry standard recommendation for loudness normalization, specifying an average program loudness target and companion metrics: **Loudness Range (LRA)** and **Maximum True Peak Level** [web:196][web:205].
- Standard reference targets: integrated loudness of **-23 LUFS** (broadcast) is the classic EBU R128 target, though social/streaming platforms often use different targets (e.g., -14 to -16 LUFS is common for streaming/social, louder than broadcast) — target should be configurable per output platform, not hardcoded [web:196][web:209].
- **FFmpeg's `loudnorm` filter** implements EBU R128 loudness normalization with configurable `I` (integrated loudness target, range -70.0 to -5.0, default -24.0), `LRA` (loudness range target, default 7.0), and `TP` (max true peak, default -2.0) parameters [web:207].
- **Single-pass vs. dual-pass mode**: single-pass is used for livestreams; dual-pass is used for file-based normalization and is more accurate. Dual-pass requires two FFmpeg invocations — first a measurement-only pass (`print_format=json`, produces no output file, just prints measured loudness stats to stderr), then a second pass supplying those measured stats (`measured_I`, `measured_LRA`, `measured_TP`, `measured_thresh`) back into the filter for the actual normalization + output [web:200][web:209].
- **True peak limiting mechanics**: to accurately detect true peaks (inter-sample peaks that simple sample-peak metering misses), the audio is internally upsampled to 192kHz; a look-ahead limiter (100ms look-ahead in FFmpeg's implementation) calculates the minimum gain reduction needed and reacts before each peak, avoiding audible pumping artifacts even under several dB of reduction [web:209].
- Example dual-pass FFmpeg command sequence [web:200]:
  ```
  # Pass 1: measure
  ffmpeg -i input.mp4 -af loudnorm=I=-23:TP=-2:LRA=7:print_format=json -f null -
  # Pass 2: apply using measured values
  ffmpeg -i input.mp4 -af loudnorm=I=-23:TP=-2:LRA=7:measured_I=-20.40:measured_LRA=8.40:measured_TP=0.02:measured_thresh=-30.86:linear=true -ar 48k output.mp4
  ```

## Safe areas: title-safe and action-safe zones
- Origin: broadcast standards (SMPTE RP 27.3/RP 8/RP 13, ITU-R BT.1973) developed to compensate for CRT television overscan, which could crop 5-10% of the visible picture at the edges [web:211][web:212].
- **Classic percentages** (still widely used as defaults in editing software safe-guide overlays): **Action-safe = 90%** of frame (5% margin per edge) — all significant motion/action should stay within this; **Title-safe = 80%** of frame (10% margin per edge) — all text/logos/critical graphics belong here [web:211][web:216].
- **Updated SMPTE standard (2009, ST 2046-1/RP 2046-2)**: redefined Safe Action Area as 93% width/height, while Safe Title Area remains 90% — note there are now *two* safe title areas to track in a 16:9 frame (a 16:9-specific one, and a 4:3 "center cut protected" one for downconversion scenarios); this nuance causes ongoing confusion among producers still using older 80/90% conventions [web:212].
- **EBU's own recommendation (Tech 3299/R095)**: slightly different numbers — action-safe area at 3.5% margin (93% of frame), graphics-safe area at 5% margin (90% of frame), applied uniformly top/bottom/left/right [web:223][web:218].
- **Social/vertical-specific safe zones (2025-2026 practical guidance)**: platform UI chrome (TikTok's like/comment/share buttons, caption bar, creator info badge) covers approximately 20-30% of the vertical frame — meaning the *only guaranteed safe space* on a 1080×1920 vertical video is roughly the center 80% (title-safe zone), with specific exclusion zones: top-left 10-15% (creator info), bottom 15-25% (auto-captions), right edge 10-15% (engagement buttons) [web:214][web:211].
- **Concrete pixel math for 1080×1920 (9:16)**: action-safe = ~972×1728px centered; title-safe = ~864×1536px centered [web:214].
- **Practical framing rules synthesized from safe-zone guidance** [web:214]:
  - Center subjects horizontally/vertically within the action-safe zone (90%) — vertical video demands centered composition (unlike horizontal's rule-of-thirds), since platform UI flanks both sides and top/bottom.
  - Position talking-head eye-line in the upper third (~30-35% down from top) for natural headroom while avoiding top UI overlays.
  - Reserve the entire bottom 25% of frame exclusively for platform-generated captions — never place custom graphic text there, to avoid double-text overlap.
  - Place all custom on-screen text/graphics in the upper or middle third, within the title-safe (80%) zone.

## Automated safe-area QC tooling (industry reference)
Broadcast-grade QC platforms (e.g., Venera Technologies' Pulsar/Quasar + QCtudio review interface) allow defining custom safe regions and **automatically detecting and flagging violations** frame-by-frame, with a browser-based review interface for annotating and exporting violation timelines back into editing software (Premiere/DaVinci Resolve) for correction — demonstrating that automated safe-area conformance checking (not just manual overlay guides during editing) is an established, buildable QC category [web:222].

## Render conformance checklist (synthesized for NLKE-SAG)
A pre-publish QC gate should programmatically verify, per output rendition:
1. **Loudness**: integrated loudness within target LUFS range for the destination platform (configurable per platform — YouTube/TikTok/Instagram may have differing informal targets); true peak below the target ceiling (e.g., -2 dBTP) using FFmpeg's `loudnorm` dual-pass measurement.
2. **Safe areas**: all caption text and any burned-in graphic overlays fall within the title-safe zone (80% center) for the target aspect ratio; primary subject (from the reframing/tracking pipeline in docs 02-03) stays within the action-safe zone (90% center) — this check can reuse the same bounding-box data already computed during reframing.
3. **Platform-specific exclusion zones**: for vertical (9:16) output specifically, verify no critical content sits in the bottom 25% (caption zone), top-left 15% (creator-info zone), or right-edge 10-15% (engagement-button zone) if targeting TikTok/Reels/Shorts.
4. **Artifact/encoding verification**: basic sanity checks on final render (correct resolution/frame rate/codec match job spec, no truncated/corrupted output, expected duration matches source edit decision list) before marking a job as render-complete and eligible for publish.

## Recommendation for NLKE-SAG
Build an automated conformance-check stage between "render complete" and "eligible for publish" that runs FFmpeg's `loudnorm` dual-pass measurement against configurable per-platform LUFS/TP targets, and cross-references the same bounding-box/caption-position data already produced during the reframing and captioning pipeline stages (docs 03-04) against the title-safe/action-safe zone percentages — reusing existing pipeline data rather than re-analyzing the final render from scratch. Fail/flag jobs that violate either check before they reach the publish queue (doc 09's job orchestration layer).
