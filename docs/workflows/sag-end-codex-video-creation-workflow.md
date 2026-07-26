# SAG End-to-End Codex Video Creation Workflow

This is the reusable, export-only production contract for turning a GitHub
repository into an evidence-backed video. Codex coordinates the workflow; the
SAG engine, project revision, receipts, and observed media remain authoritative.

## Workflow

```text
Codex direction
  -> bounded repository evidence + revision hash
  -> Omni structured creative brief
  -> human brief review
  -> Omni structured storyboard
  -> human storyboard approval receipt
  -> Omni by default / Veo for explicit specialist controls
  -> Lyria music + Gemini TTS narration
  -> download -> hash -> ffprobe -> observation
  -> revision-checked timeline insertion
  -> captions + audio mix + 9:16 finishing
  -> verified render
  -> human release review
  -> local export (publishing disabled)
```

The Director panel preserves the evidence, brief, storyboard, approval, and
queue state across Edit, Context, and System. A proposal is never treated as a
completed asset, and provider completion is never treated as verification.

## Planning contract: Codex and Omni

Codex collects a bounded repository snapshot and redacts recognizable secret
patterns before a model sees it. README text, manifests, and file names are
delimited as untrusted data. The evidence hash is copied into every brief,
storyboard, receipt, and generated-asset provenance record.

Omni planning prompts follow Google's Gemini prompt-design guidance:

- Put the role and critical factuality constraints first.
- Separate production request, evidence context, task, and output contract.
- Make the task direct and define ambiguous parameters such as duration and
  target platform.
- Require structured JSON using the Pydantic-derived JSON schema rather than
  relying on prose to describe complex output.
- Chain the work as evidence -> brief -> storyboard instead of asking one
  prompt to perform the entire production.
- Reject malformed output, missing evidence references, overlapping scenes,
  duration overflow, or an evidence-revision mismatch.

Official reference: <https://ai.google.dev/gemini-api/docs/prompting-strategies>
and <https://ai.google.dev/gemini-api/docs/structured-output>.

## Generation routing

Use `gemini-omni-flash-preview` as the default scene generator. It is the
preferred route for coherent multimodal generation, readable text direction,
and follow-up conversational editing. Route a scene to Veo 3.1 only when it
needs first/last-frame control, extension, reference-image behavior, legacy
pipeline compatibility, or a deliberately specialized cinematic shot. Veo
Lite is an explicit preview choice, not a silent production default.

Official reference: <https://ai.google.dev/gemini-api/docs/video>.

## Omni scene prompt contract

Each Omni scene prompt explicitly supplies:

- purpose;
- subject, action, environment, and context;
- continuity and visual style;
- composition and provider-supported aspect ratio;
- natural-language timing;
- native ambience and motivated effects;
- repository evidence references;
- a single continuous, unbroken scene unless a montage is intentional.

Narration, music, and captions are generated or composed separately, so the
scene prompt explicitly excludes dialogue, voiceover, captions, watermarks,
and invented product features. Omni receives a video response format with the
requested `9:16` or `16:9` aspect ratio and URI delivery for bounded download.

Official reference: <https://ai.google.dev/gemini-api/docs/omni>.

## Veo scene prompt contract

Veo receives the same evidence-bound scene intent using Google's video prompt
anatomy: subject, action, scene/context, camera angle and movement, lighting,
mood, visual style, timing, and a separate audio sentence. The API receives a
separate negative prompt made of unwanted elements such as `watermark,
distorted typography`; it does not use instructions such as `no` or `don't`.

Official reference:
<https://cloud.google.com/vertex-ai/generative-ai/docs/video/video-gen-prompt-guide>.

## Human and verification gates

1. Brief review may edit or save versions without authorizing generation.
2. Storyboard approval is bound to the current project and evidence revisions.
3. Scene generation requires the matching human confirmation.
4. Provider output must be bounded HTTPS or inline media, then downloaded,
   hashed, imported, probed, observed, and inserted through canonical commands.
5. Rendering validates the project revision and produces a hashed artifact.
6. Export requires review; this workflow does not request YouTube OAuth and
   cannot publish.

Retries deduplicate on receipt and provider operation ID. A scene may be
regenerated without invalidating unrelated verified scenes.

## Acceptance output bundle

The reusable bundle contains the redacted evidence snapshot and revision,
creative brief, storyboard, scene prompts and model IDs, provider operation
receipts, observed asset hashes, canonical timeline revision, narration and
music provenance, caption data, render receipt, and final artifact hash. Keep
credentials, `.env.local`, OAuth tokens, and service-account JSON outside the
bundle.
