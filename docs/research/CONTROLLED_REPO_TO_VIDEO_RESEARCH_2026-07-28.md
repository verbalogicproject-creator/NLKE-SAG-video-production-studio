# Controlled repo-to-video research

**Research date:** 2026-07-28
**Status:** Phase 1 research complete; no implementation decision is implied
**Target:** a verified 30-second, native 9:16 SAG short that is cinematic,
screenshot-grounded, factually authentic, and intelligibly narrated

## Executive conclusion

The production system should not bind itself to one video model or one long
prompt. The most controllable design is a **provider-neutral shot contract**
that is compiled into model-specific requests, followed by deterministic SAG
assembly.

The generator should create motion, environment, depth, transitions, and
visual metaphor. Authentic SAG screenshots should serve two distinct roles:

1. **Reference inputs** that guide the visual language of generated shots.
2. **Protected evidence pixels** composited by SAG without regeneration when
   actual UI, text, controls, or product claims must remain readable.

No current generator should be trusted to redraw factual application UI. The
official LTX guide explicitly says readable text and logos are unreliable, and
the user's previous generated “Chamber” UI already demonstrates the failure
mode. Generated UI may be decorative, but only preserved screenshots can prove
the product.

For the first production experiment, the strongest candidates are:

- **Gemini Omni Flash** for low-cost, screenshot/reference-aware drafts and
  conversational refinement.
- **LTX-2.3 Fast/Pro** for native 1080x1920 image-to-video, first/last-frame
  control, explicit camera motion, predictable price, and longer shots.
- **Veo 3.1 Fast/Standard** for selected hero shots where reference fidelity
  and finish justify the higher cost.
- **Wan 2.2 5B/A14B through direct fal.ai image-to-video** for cheap five-second
  connective shots and experiments—not as the sole 1080p production path.

The existing Hugging Face `InferenceClient(provider="fal-ai")` path is useful
for simple, low-friction text-to-video experiments. It is not currently a
sufficient abstraction for the required production controls.

## The sound failure: two concrete causes

There are two separate sound issues, and both matter:

1. `scripts/build-repo-to-video-example.sh` deliberately creates a 440 Hz sine
   track. That fixture hum is not narration. The old QC gate proved only that an
   AAC stream and spectral activity existed; it did not prove speech.
2. In the supplied fal.ai screenshot, **Generate Audio is switched off**. A job
   launched with that setting should be expected to return silent video.

These facts explain the deterministic fixture and the pictured fal.ai setting.
They do **not** by themselves prove the waveform-level cause of the separate
60-second candidate's perceived hum. That candidate also passed through generic
track placement and `amix` rendering without semantic narration/music roles or
intelligibility QC, so its exact audio provenance must be traced by asset hash
before assigning one cause.

The live repo-to-video flow does dispatch music and TTS operations separately,
but it does not yet establish that the final 30-second render contains the
approved narration mixed over music. Stream presence must therefore never be
the production audio acceptance test.

The production rule should be:

```text
frozen narration script -> dedicated TTS asset -> speech observation/ASR
music direction -> separate music asset
scene generator audio -> optional ambience/SFX only
speech + ducked music + selected ambience -> deterministic final mix
```

For the first local narration adapter, evaluate the existing
`/storage/emulated/0/models/onnx/kokoro-82m-onnx` assets. Background music
should come from a managed licensed-media importer rather than a generic web
scraper: every downloaded track must retain source URL, author, license and
attribution requirements, retrieval timestamp, original hash, and normalized
asset hash. “Royalty-free” must not be interpreted as license-free.

Acceptance must include transcript agreement, speech/non-tonality detection,
silence and dropout checks, loudness/true-peak checks, and complete human
playback with sound.

## Official prompting guidance that generalizes

### One focused shot per generation

Google recommends dedicating a short-video prompt to one focused moment instead
of chaining several unrelated events. A 30-second story should therefore be
assembled from bounded shots, not requested as one undifferentiated generation.
See [Google's video-generation best practices](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/best-practice).

### A structured prompt grammar

Across Google's and LTX's official guides, the recurring controllable elements
are:

```text
shot/framing
+ subject or protected reference identity
+ concrete visible action
+ environment and spatial relationship
+ camera movement relative to the subject
+ lighting, palette, texture, and atmosphere
+ temporal pacing and end state
+ audio intent
+ exclusions
```

LTX recommends establishing the shot, setting the scene, describing action,
defining characters, identifying camera movement, and describing audio. It
also recommends present-tense, flowing prompts of roughly four to eight
sentences and warns against overloaded scenes and conflicting lighting. See the
[official LTX prompting guide](https://docs.ltx.io/api-documentation/implementation-guides/prompting-guide).

Google's Veo guide covers shot size, camera position and movement, lens/effects,
lighting, art direction, ambiance, temporal pacing, audio, cinematic editing
terms, and negative prompts. For Veo negative prompts, Google recommends listing
the unwanted concepts rather than writing instructions such as “don't.” See the
[official Veo prompt guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/video-gen-prompt-guide).

### Image-to-video prompts should mostly describe motion

Google, LTX, and Wan guidance converge on this point: the source image already
establishes appearance, layout, lighting, and style. Re-describing all of it can
introduce conflict. Image-to-video prompts should emphasize:

- camera motion;
- subject/object motion;
- environmental motion;
- pacing and end state;
- desired ambience or effects.

Google describes camera-only motion as the simplest and most reliable way to
add dynamism. LTX advises matching the input aspect ratio to the target. Wan's
published image-to-video formula is essentially “motion description + camera
movement.” Sources: [Google best practices](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/best-practice),
[LTX image-to-video guide](https://docs.ltx.io/open-source-model/usage-guides/image-to-video),
and [fal.ai's Wan 2.2 guide](https://fal.ai/models/fal-ai/wan/v2.2-a14b/image-to-video).

### Provider-specific syntax must remain provider-specific

There is no safe universal text formatter:

- Google recommends avoiding quotation marks for dialogue in some Veo flows to
  reduce unintended on-screen text.
- LTX explicitly uses quotation marks for dialogue.
- Gemini Omni accepts natural-language time events and `[0-3s]`-style timecode
  blocks, plus `<FIRST_FRAME>` and `<IMAGE_REF_N>` media-role tags.
- Some fal.ai endpoints expose a separate negative-prompt field; Gemini Omni
  currently does not.

Therefore `repo-to-video-1` should store semantic fields and compile them through
a provider profile. It should not store one “universal final prompt.”

### Control by invariants, not adjective volume

For continuity across shots:

- freeze and repeat the unchanged continuity contract;
- vary only the shot action, camera, and environment fields;
- reuse a seed when the endpoint supports it;
- bind every reference to a declared role;
- use first/last frames for a specific transition where supported;
- change one variable per refinement pass;
- keep accepted shots immutable and regenerate only rejected shots.

Seeds improve repeatability but are not proof of exact reproduction. The final
artifact still needs hashes and observation.

## Model and platform findings

Prices below are current public list prices and can change. Thirty-second costs
are illustrative raw-output equivalents before retries, rejected alternatives,
storage, audio, or post-production.

| Candidate | Control surface | Main limitations | Approx. 30s raw output | SAG opinion |
|---|---|---|---:|---|
| Gemini Omni Flash | Text/image/video input, multiple image references, 9:16, timecodes, generated audio, stateful conversational editing | Preview; no first/last interpolation or extension; no seed/negative field; regional editing limits | Google direct: about $3 at 720p; fal: about $3.90 | Best rapid reference-aware ideation/refinement candidate |
| Veo 3.1 | Up to 3 reference images, image start frame, first/last interpolation, 9:16, 720/1080/4K, native audio, extension | Clips are 4/6/8s; preview variants and higher cost; generated text remains unsuitable as evidence | Lite 1080: $2.40; Fast 1080: $3.60; Standard 1080: $12 | Best selected hero-shot/final-quality candidate |
| LTX-2.3 Fast | 9:16 through 4K, I2V, first/last frame, explicit camera motion, audio, 24/25/48/50fps, 6-20s at 1080/24-25 | Fast lacks retake/extend/audio-to-video endpoints; generated text/logos unreliable | 1080: $1.80 | Best first controlled prototype |
| LTX-2.3 Pro | Same core generation controls, higher fidelity; retake/extend/audio-to-video available | 6/8/10s shots; hosted API and self-hosted weights have distinct terms | 1080: $2.40 | Strong final-shot and repair path |
| Wan 2.2 5B | Cheap T2V/I2V, seed and generation controls on direct fal endpoint, up to 5s 720p/24fps | 720p; short; no native production narration; HF wrapper currently sends text only | Direct fal: about $0.90 for six 5s clips | Useful preview/connective-shot candidate |
| Wan 2.2 A14B | T2V/I2V, start/end images on direct fal endpoint, more capable motion | 480/580/720p; heavier local requirements | Direct fal 720p: about $2.40 | Useful when Wan look/motion wins an A/B test |
| I2VGen-XL | Image-guided cascaded diffusion; research checkpoint | 2023-era, 1280x720 target, no hosted HF provider, no audio, research/non-commercial model-card restriction | Self-hosting only | Exclude from the production shortlist |

### Gemini Omni Flash

“Omni” is no longer ambiguous in this context: the current Google model is
`gemini-omni-flash-preview`, and fal.ai exposes
`google/gemini-omni-flash/image-to-video`.

Google documents native multimodal input, 9:16 output, image/reference-to-video,
generated audio, conversational video editing through `previous_interaction_id`,
natural-language timing, and media-role tags. It also documents important
limitations: no video extension, no first/last-frame interpolation, no audio
reference upload, no seed/temperature/top-p/negative-prompt fields, and limited
regional video editing. See [Gemini Omni Flash documentation](https://ai.google.dev/gemini-api/docs/omni).

Google lists approximately $0.10 per second of 720p output. The corresponding
fal.ai endpoint lists approximately $0.13 per second and supports 3-10 second
clips. See [Google pricing](https://ai.google.dev/gemini-api/docs/pricing) and
[fal.ai Omni pricing/schema](https://fal.ai/models/google/gemini-omni-flash/image-to-video).

**SAG inference:** Omni is exceptionally well matched to iterative art
direction and screenshot/style references. It is not the path for exact UI
pixels, and its lack of interpolation/extension means SAG should still assemble
separate shots.

### Veo 3.1

Veo 3.1 supports 9:16, 720p/1080p/4K variants, 4/6/8-second clips, native audio,
up to three content/style reference images, image-to-video, first/last-frame
interpolation, and extension of Veo-generated clips. See the
[official Veo 3.1 API guide](https://ai.google.dev/gemini-api/docs/veo).

Current direct Gemini pricing with audio is $0.05/$0.08 per second for Lite at
720/1080, $0.10/$0.12 for Fast, and $0.40 at 720/1080 for Standard. Google notes
that preview models can change and have more restrictive limits. See
[Google's current pricing](https://ai.google.dev/gemini-api/docs/pricing).

**SAG inference:** use Fast for candidates and Standard only after a shot is
compositionally locked. Reference images can preserve product appearance, but
authentic text/UI should still be overlaid from observed screenshots.

### LTX-2.3

LTX-2.3 supports native 1080x1920, 1440x2560, and 2160x3840 portrait output,
first/last-frame image-to-video, 24/25/48/50fps, generated audio, and an explicit
camera-motion request field. Fast reaches 20 seconds only at 1080p/24-25fps;
Pro generation is limited to 6/8/10-second options but unlocks audio-to-video,
retake, extend, and reframe. LTX itself recommends Fast for exploration and Pro
for final output. See [LTX supported models](https://docs.ltx.io/models) and the
[image-to-video API](https://docs.ltx.io/api-documentation/api-reference/video-generation/image-to-video).

Hosted API list price at 1080p is $0.06/s Fast and $0.08/s Pro. See
[LTX pricing](https://docs.ltx.io/pricing).

The code repository uses Apache-2.0, while the current LTX-2.3 Hugging Face model
weights show the LTX-2 Community License Agreement. Hosted fal/LTX APIs label
their endpoints for commercial use. Licensing should therefore be recorded per
deployment route instead of treating “LTX” as one license. Sources:
[official code license](https://github.com/Lightricks/LTX-Video/blob/main/LICENSE)
and [official model card](https://huggingface.co/Lightricks/LTX-2.3).

**SAG inference:** LTX-2.3 has the most practical combination of cost, native
vertical resolution, start/end control, audio, and explicit camera control for
the first engineering prototype.

### Wan 2.2 series

The official Wan repository provides:

- T2V-A14B and I2V-A14B at 480p/720p;
- TI2V-5B at 720p/24fps;
- S2V-14B using image + audio + optional text, with optional pose video;
- Animate-14B for character animation/replacement.

Local execution is not phone-class: the official examples cite at least 24 GB
GPU memory for TI2V-5B and substantially larger configurations for some 14B
flows. See the [official Wan2.2 repository](https://github.com/Wan-Video/Wan2.2).

Direct fal endpoints expose materially more controls than the current SAG HF
adapter: image input, optional end frame, seed, frame count/FPS, inference steps,
guidance, interpolation, quality, and write mode. The 5B endpoint is currently
$0.15 per video, while A14B 720p is listed at $0.08/s. See the
[fal Wan 5B I2V schema](https://fal.ai/models/fal-ai/wan/v2.2-5b/image-to-video/api)
and [A14B pricing/guide](https://fal.ai/models/fal-ai/wan/v2.2-a14b/image-to-video).

**SAG inference:** Wan is useful and affordable, but the existing
`InferenceClient.text_to_video()` call throws away the very controls required
for screenshot grounding. Wan should be tested through a provider-native I2V
adapter or not described as image-conditioned.

### I2VGen-XL

I2VGen-XL is a cascaded 2023 image-to-video diffusion model intended to preserve
input-image semantics and refine output to 1280x720. Its official Hugging Face
model card says it is not deployed by any Inference Provider and is intended
for research/non-commercial use. It has no production audio, vertical-1080,
first/last-frame, or hosted pricing story. See the
[official model card](https://huggingface.co/ali-vilab/i2vgen-xl) and
[paper](https://arxiv.org/abs/2311.04145).

**SAG inference:** it is valuable historical/research context, but using it in
the product would add deployment and licensing burden while reducing quality
and control relative to current candidates.

## fal.ai and Hugging Face: how they fit

fal.ai is a hosted generative-media platform, not a model. It exposes many
vendors' models behind provider-specific schemas, managed file upload, queued
long-running jobs, polling/webhooks, and per-model output pricing. Its official
guidance recommends queues/webhooks rather than holding a request open for long
generations and warns not to expose its API key in a browser. See a representative
[fal model API page](https://fal.ai/models/google/gemini-omni-flash/image-to-video/api)
and [fal pricing](https://fal.ai/pricing).

The supplied screenshots are consistent with a ByteDance Seedance image-to-video
playground: start image, optional end image, resolution, duration, and a
Generate Audio switch. Seedance 2.0 additionally exposes a reference-to-video
endpoint accepting up to nine images, three video clips, and three audio files,
but its 720p-with-audio list price is $0.3034/s ($0.2419/s Fast). See the
[official fal Seedance 2.0 reference](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-seedance-2.0-text-to-video).
It is promising for later A/B testing, especially because multiple screenshots
can have explicit `[ImageN]` roles, but it is not the cheapest first experiment.

Hugging Face Inference Providers is a proxy and billing layer. Routed requests
use `HF_TOKEN`, consume HF credits, and are billed at provider rates without an
HF markup. A custom provider key can also be routed through HF. See
[HF pricing and billing](https://huggingface.co/docs/inference-providers/pricing).

Important boundary:

- The generic `huggingface_hub.InferenceClient` now has an `image_to_video`
  method.
- The current Hugging Face fal provider page lists **Text To Video**, not
  Image To Video, as its supported video task.
- Its common video types cover prompt, negative prompt, frame count, inference
  steps, guidance, seed, and target size—not fal-specific fields such as end
  image, generated audio, multi-reference roles, or shot type.

Sources: [HF client reference](https://huggingface.co/docs/huggingface_hub/package_reference/inference_client),
[HF inference types](https://huggingface.co/docs/huggingface_hub/package_reference/inference_types),
and [HF's fal provider page](https://huggingface.co/docs/inference-providers/en/providers/fal-ai).

The existing `HF_TOKEN` authenticates HF-routed calls. It is not a fal.ai API
key for direct `fal.run` calls. Full fal-native control will require a deliberate
direct-fal credential and billing decision or a verified future HF provider
mapping—never silent fallback.

## NVIDIA Build/NIM: useful adjacent capability, not this A/B provider

The current NVIDIA NIM visual-model catalog exposes Stable Video Diffusion for
image-to-video, plus visual understanding and grounding models. It does not
list Gemini Omni, Veo, or LTX-2.3 as hosted generation endpoints, so an
`NVIDIA_API_KEY` is not an equivalent fallback for the requested three-model
comparison. See the official [NVIDIA visual-model API catalog](https://docs.api.nvidia.com/nim/reference/visual-models-apis)
and [NIM catalog quickstart](https://docs.api.nvidia.com/nim/docs/api-quickstart).

NVIDIA can still add value later as a provider-neutral QC/evaluation adapter:
video understanding, OCR/grounding, reference-region comparison, and artifact
classification are better fits than silently replacing the selected generator.
Stable Video Diffusion may be a cheap motion-baseline experiment, but its
published NVIDIA endpoint scales the input to 1024x576 and exposes only narrow
motion controls, so it is not a native 9:16 production candidate for
`repo-to-video-1`. See the official [Stable Video Diffusion request schema](https://docs.api.nvidia.com/nim/reference/stabilityai-stable-video-diffusion-infer).

## Live A/B result

The controlled fal.ai A/B/C harness was revised to one six-second 9:16
image-to-video request each through Gemini Omni Flash, Veo 3.1, and LTX-2.3,
with provider retries disabled. Native audio is disabled for Veo and LTX;
Omni's unavoidable raw audio is excluded from evaluation and stripped from its
evaluation derivative. The conservative documented maximum cost is $2.46. The
selected input is
`latest/Screenshot_20260727_082657.jpg` (SHA-256
`d2f31a37875753aabcb73904788a22d6b9009947583124be7d29ba58094dc709`).

Two preflight attempts stopped before inference because fal managed-storage
initiation returned HTTP 403, `User is locked. Reason: Exhausted balance`; both
cost $0.00. After the correct workspace balance was restored, all three frozen
one-shot requests completed without provider retries:

| Model | Request | Observed output | Latency | Documented cost |
|---|---|---|---:|---:|
| Gemini Omni Flash | `019fa92d-dbec-7781-89d2-b9c7bc25d691` | 720x1280, 24 fps, 6.016 s; raw AAC stripped from evaluation derivative | 82.063 s | $0.78 |
| Veo 3.1 | `019fa92f-1aad-7db1-9505-bbba639d4e0f` | 720x1280, 24 fps, 6.000 s; no audio | 60.117 s | $1.20 |
| LTX-2.3 | `019fa930-057c-7392-93d9-c6dbf8d533e3` | 1080x1920, 24 fps, 6.042 s; no audio | 69.627 s | $0.48 |

The documented total is $2.46. Preliminary 1/3/5-second frame inspection found
that Omni produced the most cinematic reframing into a desktop-monitor scene
while largely retaining the source UI; Veo preserved the UI composition most
steadily while adding restrained cyan environmental framing; LTX lost the UI
by approximately three seconds and resolved into a teal field. Omni and Veo
still rewrote visible branding or text, confirming that reference conditioning
cannot replace protected canonical UI composites.

Raw candidates, silent evaluation copies, hashes, probes, representative
frames, sanitized receipts, and the comparison report are under
`.sag-video/ab-omni-veo-ltx-2026-07-28/`. No candidate was promoted and the
accepted baseline was not modified.

### Refined Omni overlay-ready probe

A follow-up Omni request (`019fa93c-1a3f-7fb0-94ae-4e6f9118bc7e`) tested a
more explicit replacement-ready contract: slow dolly-out, front-facing planar
display, visible corners, no crossing light bands, static cyan practical
lighting, and silent evaluation. It completed in 46.844 seconds for a
documented $0.78. The raw result is 720x1280 at 24 fps for 6.016 seconds with
native AAC; the evaluation derivative is exactly 6.000 seconds with no audio.

Representative frames show a materially better plate for deterministic
composition. From approximately two seconds onward, the monitor rectangle is
fully visible, front-facing, unobstructed, and surrounded by cinematic depth;
the earlier Veo-style crossing light band is absent. Omni still invents browser
chrome and rewrites branding/UI text, so the generated screen content is not
evidence. The four-corner display plane is nevertheless plausible for a later
tracked homography that replaces it with the canonical screenshot. Artifacts
are under `.sag-video/omni-overlay-ready-2026-07-28/`; no candidate was
promoted.

## Current SAG implementation findings

The product already has useful foundations, so Phase 2 should extend rather
than rebuild them:

- `PromptStudio.tsx` already presents versioned prompt modules, hashes, routing,
  resolved scene prompts, model capabilities, and editable global inputs.
- `repo_to_video.py` already models creative briefs, per-scene prompts, evidence
  references, spatial regions, provider selection, and a resolved prompt hash.
- `generative.py` already isolates Google and HF provider boundaries.
- managed media intake, observation, receipts, timeline commands, rendering,
  and representative-frame QC already exist elsewhere in SAG.

The research-relevant gaps are concrete:

1. `RepoVideoRequest` and the web route still default to 60 seconds.
2. Reference IDs exist in request models but are not delivered to any current
   video provider call.
3. Gemini Omni is always dispatched as `text_to_video` with prompt text only.
4. The Veo call does not pass initial, final, or reference images.
5. The HF/fal adapter calls only `text_to_video(prompt, model=...)`; it discards
   duration, aspect ratio, negative prompt, first/last frame, and references.
6. Music and narration are dispatched as separate assets, but the flow does not
   yet prove their deterministic placement, mixing, or final-render audibility.
7. The offline example's sine tone can still look superficially “audio valid.”
8. The Prompt Studio has no preset identity/version, structured shot controls,
   provider-capability diff, reference-role editor, seed/run controls, or cost
   estimate.

## Candidate repo-to-video algorithm for discussion

This is the research synthesis to refine before Phase 2 planning:

1. **Observe evidence:** ingest repository evidence and screenshots through
   managed intake; normalize, hash, classify, and redact sensitive regions.
2. **Resolve a versioned theme:** choose `repo-to-video-1`; pin brand, palette,
   typography, narrative grammar, audio profile, exclusions, safe areas, and QC.
3. **Freeze a 30-second story contract:** create bounded single-moment shots
   whose durations sum exactly to 30 seconds; freeze narration separately.
4. **Declare reference roles per shot:** `style_reference`, `subject_reference`,
   `first_frame`, `last_frame`, `protected_composite`, or `absent`.
5. **Negotiate provider capabilities:** choose a provider/endpoint only when it
   supports the declared roles, resolution, duration, audio policy, and budget.
   Unsupported controls must fail visibly or compile to an explicitly approved
   deterministic fallback.
6. **Compile provider-specific prompts:** merge immutable theme continuity with
   the shot's action/camera/timing and the provider's syntax. Save the compiled
   request hash, endpoint, model version, seed, and reference hashes.
7. **Generate low-cost candidates first:** produce alternatives with Omni,
   LTX Fast, or Wan. Observe every returned artifact. Refine one variable at a
   time; promote selected shots to LTX Pro or Veo only when justified.
8. **Preserve factual UI:** composite authentic screenshot regions over or
   within the selected generated shots. Do not use generated pixels as product
   evidence.
9. **Build audio independently:** generate and observe TTS from the frozen
   script, obtain music separately, select optional ambience, then mix with
   ducking and fades.
10. **Assemble deterministically:** FFmpeg constructs the exact 1080x1920,
    30-second edit with explicit timing, crops, transforms, overlays, captions,
    and track order.
11. **Verify and approve:** run visual, audio, transcript, duration, frame,
    source-asset, receipt, and SHA-256 checks; then require a full human watch
    with sound before replacing the baseline.

## `repo-to-video-1` preset/library direction

The first preset should be a versioned production policy, not merely a prompt
string. A future library entry should eventually contain:

```text
identity + semantic version
supported video purpose and target platforms
narrative beats and shot archetypes
global visual continuity contract
brand/safe-area/authenticity rules
reference-role policy
provider profiles and fallback rules
prompt field schema and provider compilers
audio/narration/music policy
default candidate counts and budget bands
QC and human-approval gates
```

The Prompt Studio upgrade should be discussed around four layers:

1. **Preset layer:** select/fork/version `repo-to-video-1` and show inherited
   values.
2. **Continuity layer:** edit global brand, look, exclusions, and audio policy.
3. **Shot layer:** edit shot, action, camera, timing, references, protected
   regions, model/endpoint, seed, and candidate count.
4. **Compiled layer:** read-only exact provider payload, omitted/unsupported
   controls, estimated cost, reference hashes, and resulting revision hash.

This preserves the current prompt editor's useful source/resolved distinction
while making control explicit and reusable for later tutorial, product-launch,
portfolio, incident, receipt, and documentary presets.

## Decisions required before Phase 2 planning

1. **First provider experiment:** LTX-2.3 Fast direct, Gemini Omni direct, or a
   small A/B test of both? Research recommendation: A/B one identical 6-8s shot.
2. **fal.ai account boundary:** continue with HF-routed text-only experiments,
   or authorize a direct fal.ai integration and key for provider-native I2V?
3. **Production hero model:** allow Veo only for selected shots, or include it
   in the first A/B test?
4. **Audio policy:** recommendation is native model audio for ambience only;
   dedicated TTS remains the authoritative narration.
5. **Screenshot policy:** confirm that generated approximations are decorative
   and only exact composites count as evidence.
6. **Preset scope:** keep `repo-to-video-1` project-shipped and read-only at
   first, or allow Studio users to fork it immediately?
7. **Budget gate:** choose a per-candidate and per-30-second production ceiling,
   including retries.
8. **Credential/deployment route:** direct Google, direct LTX, direct fal.ai,
   HF-routed fal.ai, or a deliberately supported subset of them.

No model calls, purchases, credentials, or implementation changes were made
during this research phase.
