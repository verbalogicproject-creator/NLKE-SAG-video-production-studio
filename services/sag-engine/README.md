# SAG Video

SAG Video is a video-production GUI and terminal surface built on one canonical
semantic timeline. Imported media can be edited, queued for FFmpeg rendering,
and inspected before the output becomes observed success.

## What is implemented

- Browser timeline, program monitor, semantic selection, property inspector,
  receipts, and terminal pairing.
- Multiple project creation/opening and responsive phone section navigation.
- Professional matte editor styling with a mobile media reel and fixed
  thumb-reachable section navigation.
- Continuous imported-proxy sequence playback across clip boundaries and gaps,
  with a moving timeline playhead and seeking.
- Revisioned asset insertion, move, split, source trim, delete, visual fit,
  gain/mute, title editing, and compensating undo.
- Touch-friendly timeline edge trimming and snapping plus direct monitor move,
  resize, and rotation controls backed by semantic commands.
- Stable project, track, clip, title, and asset identities.
- Integer media time at 120,000 ticks per second.
- Revision-checked and idempotent semantic commands with compensating undo.
- Migration-driven normalized SQLite revisions, receipts, observations, jobs,
  and provider-neutral creative-run records with atomic units of work.
- CLI and MCP surfaces over the same HTTP commands used by the GUI.
- Immutable exact-revision render specifications and allowlisted FFmpeg
  compilation for real clips, trims, transforms, titles, and audio. Callers
  cannot supply filters or shell code.
- One persistent bounded render worker with polling, cancellation requests,
  crash interruption state, atomic artifact finalization, and stable playback.
- Receipt lifecycle separating dispatch, rendering, observation, failure,
  timeout, denial, and success.
- Output-only verification using `ffprobe` and a decoded encoded frame.
- Optional invite token and single-use terminal pairing codes.
- Separate observer service entry point for split deployment.
- Ranked talking-head short discovery with exact word evidence, English/Hebrew
  transcription adapters, optional OpenAI-compatible scoring, FFmpeg
  silence/scene analysis, and optional MediaPipe face tracking.
- Five auditable 9:16 drafts by default, with immutable source lineage,
  content-addressed media sharing, editable active-word captions, crop
  keyframes, and independent derived projects.

The first discovery target is talking-head material—podcasts, interviews,
tutorials, and demos—not arbitrary video, social publishing, or trend claims.

The current functional milestone includes real managed-media intake: a browser or CLI
upload is copied into opaque project storage, hashed, probed, bounded, and given
a generated proxy and thumbnail before it appears as observed-valid media. It
can then be inserted, previewed, and rendered from an exact canonical revision.

## Run it

Requirements: Python 3.12+, FFmpeg/ffprobe, and a build of FFmpeg with
`drawtext` and `libx264`.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
make dev
```

Open `http://localhost:8080`, import a real clip, add it to the timeline, then
click **Render**. The request returns immediately while the persistent local
worker renders and observes the output.

Click **Create Shorts** after importing a 15-second-or-longer talking-head
video. Discovery runs as a persistent job, and accepted drafts open as separate
vertical projects. Without a configured transcription provider, the job fails
with setup instructions rather than inventing transcript text.

For local, private transcription, install `whisper.cpp` and configure a
multilingual model:

```sh
export SAG_VIDEO_WHISPER_BINARY=whisper-cli
export SAG_VIDEO_WHISPER_MODEL=/absolute/path/to/ggml-small-q5_1.bin
```

Alternatively, use a remote endpoint supporting OpenAI-style verbose word
timestamps:

```sh
export SAG_VIDEO_TRANSCRIPTION_BASE_URL=https://provider.example
export SAG_VIDEO_TRANSCRIPTION_API_KEY=...
export SAG_VIDEO_TRANSCRIPTION_MODEL=whisper-1
```

Optional semantic ranking accepts any compatible chat-completions server with
JSON Schema output, including a local `llama.cpp` server:

```sh
export SAG_VIDEO_RANKING_BASE_URL=http://127.0.0.1:8081
export SAG_VIDEO_RANKING_MODEL=YOUR_MODEL
export SAG_VIDEO_RANKING_API_KEY=...
```

Set `SAG_VIDEO_START_ANALYSIS_WORKER=0` on the control service and run
`sag-video-analysis-worker` as a separate process for production. Both
processes must share the SQLite database and media directories.

For the real editor path, import a clip with Media `+`, tap **Add to timeline**,
select its stable timeline item, then play, seek, split, drag, trim, change fit
or gain, delete, and undo. These edit the server-owned project; browser playback
position alone remains local and ephemeral.

The development database and artifacts live under `.sag-video/` and are
ignored by Git.

The normalized schema, migration policy, repository protocols, and required
query/transaction behavior are specified in
[`docs/persistence-spec.md`](docs/persistence-spec.md).

## Terminal and agent use

After starting the service:

```sh
sag-video contract show --json
sag-video context show --json
sag-video command list --active --json
sag-video asset import ./screen-recording.mp4
sag-video asset list
sag-video timeline insert ASSET_ID --expected-revision REVISION
sag-video timeline split ITEM_ID --at-ticks 360000 --expected-revision REVISION
sag-video timeline move ITEM_ID --start-ticks 480000 --expected-revision REVISION
sag-video clip trim ITEM_ID --start-ticks 120000 --source-in-ticks 120000 --duration-ticks 240000 --expected-revision REVISION
sag-video clip transform ITEM_ID --scale 0.8 --rotation 12 --x 40 --y 20 --expected-revision REVISION
sag-video project show --json
sag-video title move title_intro --x 60 --y 56 --expected-revision 1
sag-video render start --revision 2
sag-video render status JOB_ID
sag-video render cancel JOB_ID
sag-video shorts generate --revision REVISION --asset-id ASSET_ID --prompt "Find the strongest practical advice"
sag-video shorts list --state pending
sag-video shorts show SUGGESTION_ID
sag-video shorts accept SUGGESTION_ID --name "Practical advice"
sag-video shorts reject SUGGESTION_ID
```

For an invite-protected instance, click **Pair terminal**, then exchange the
displayed code:

```sh
SAG_VIDEO_URL=https://YOUR_HOST sag-video pair 123456 --actor codex
```

Put the returned token in `SAG_VIDEO_TOKEN`. Both Codex and Claude Code can
launch the stdio MCP server with:

```json
{
  "mcpServers": {
    "sag-video": {
      "command": "sag-video-mcp",
      "env": {
        "SAG_VIDEO_URL": "https://YOUR_HOST",
        "SAG_VIDEO_TOKEN": "PAIRED_TOKEN"
      }
    }
  }
}
```

For the project-local Codex link included in this repository, press **Pair** and
store the short-lived token without putting it in configuration:

```sh
PYTHONPATH=src python -m sag_video.cli pair 123456 --actor codex \
  --save-token .sag-video/codex-token
PYTHONPATH=src python scripts/codex_link_preflight.py
```

Start one new Codex session from this trusted repository to load
`.codex/config.toml`. Later token refreshes do not require another restart. See
[`docs/codex-sag-link.md`](docs/codex-sag-link.md) for the acceptance workflow.

The MCP tools expose contract/context discovery, timeline inspection, editing,
short discovery/review/acceptance, render enqueue/status/cancellation,
compensating undo, and receipt inspection.
They never expose a raw FFmpeg or shell tool.

The application contract is generated from the same declared command registry
used by dispatch. Discovering commands or semantic selection does not grant
authority to execute them.

## Managed media

The browser Media `+` button uses the Android file picker. The server accepts
bounded video/audio uploads only; it never accepts a filesystem path to read on
the caller's behalf. Defaults can be configured with:

- `SAG_VIDEO_MEDIA_DIR` and `SAG_VIDEO_PROXY_DIR`
- `SAG_VIDEO_UPLOAD_LIMIT_BYTES` (default 512 MiB)

Imported source, proxy, database, and render files live under `.sag-video/` by
default and remain ignored by Git. The phone portrait layout stacks Media,
Monitor, Timeline, and Inspector into touch-reachable sections; landscape keeps
the editor grid.

## Trust boundary

- Context never grants authority.
- Unknown commands fail closed.
- A valid browser invite establishes an HttpOnly same-site cookie so native
  thumbnail and range-video requests use the same protected workspace session.
- GUI and agent edits both require an exact expected revision.
- Edit readback is explicitly marked as not independent.
- FFmpeg completion is only `awaiting_observation`.
- The observer evaluates the completed artifact rather than controller logs.
- In-process observation is labeled `in_process_development`. Set
  `SAG_VIDEO_OBSERVER_URL` and `SAG_VIDEO_OBSERVER_MODE=separate_service` for
  the split service deployment.

See [architecture](docs/architecture.md), [OpenCut audit](docs/opencut-audit.md),
and [deployment](docs/deployment.md).

## Verify

```sh
make test
```
