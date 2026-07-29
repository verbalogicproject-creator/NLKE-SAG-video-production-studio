# Repo-to-video production flow

SAG Video treats a repository as bounded evidence, not as an untrusted prompt.

1. `POST /api/projects/{project_id}/repo-to-video/evidence` validates an HTTPS
   GitHub URL and fetches a capped README, file tree, and common manifests from
   the server side.
2. Secrets and credential-like strings are redacted before evidence can reach
   the model. Repository material is not written to runtime telemetry.
3. `POST /api/projects/{project_id}/repo-to-video/director/brief` sends bounded
   evidence plus natural-language direction to an Omni creative-director pass.
   It returns a strict brief with separate Omni, Veo, music, and narration
   guidance.
4. `POST /api/projects/{project_id}/repo-to-video/storyboard` uses the reviewed
   direction to produce a strict JSON storyboard.
5. The storyboard must carry the SHA-256 evidence revision, have non-overlapping
   scenes, and cite evidence references for factual claims.
6. The proposal creates an `awaiting_user_consent` receipt. It does not mutate
   the timeline or claim that media exists.
7. After approval, the canonical command gateway generates scenes with Omni/Veo,
   creates music with Lyria, creates narration locally with Kokoro-82M ONNX, observes every
   downloaded asset, and only then commits verified assets to the timeline.

The executable generation boundary is `POST
/api/projects/{project_id}/repo-to-video/generate`; its parent receipt can be
polled at `/repo-to-video/generation/{receipt_id}`. Provider completion only
downloads a bounded HTTPS/inline output, runs canonical media observation, and
inserts only observed-valid assets through revision-checked timeline commands.
Missing output, unsafe URLs, failed probing, or failed insertion become a
terminal failure; provider completion is never publication success.

Local narration uses `SAG_KOKORO_MODEL_DIR` (default:
`/storage/emulated/0/models/onnx/kokoro-82m-onnx`) and reads its bundled
tokenizer plus `voices_arrays.npz`. It requires `espeak-ng`, `numpy`, and
`onnxruntime` only when narration is requested. The local generation receipt
records hashes, duration, chunk count, and runtime metadata; it never records
the narration transcript or base64 audio.

The candidate editor's Firebase, Socket.IO state, browser tokens, and simulated
Veo completion are intentionally not part of this flow.
