# Repo-to-video acceptance example

[`sag-video-repo-to-video-template.mp4`](./sag-video-repo-to-video-template.mp4)
is the first concrete repo-to-video deliverable. It is a 30-second, 720p
video with synchronized audio rendered through the same export/observation
shape expected of provider-generated scenes.

It is intentionally deterministic and offline so it can be used as a fixture
while Google credentials are unavailable. Rebuild it with:

```sh
scripts/build-repo-to-video-example.sh
```

The production replacement keeps the same scene/timeline contract but obtains
scene media from Omni/Veo, narration from Gemini TTS, and music from Lyria;
each output must pass media observation before publication.

The reusable production contract is documented in
[`docs/workflows/sag-end-codex-video-creation-workflow.md`](../../docs/workflows/sag-end-codex-video-creation-workflow.md).
