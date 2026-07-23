# Codex–SAG Link

Status: implementation-ready; one new Codex session is required to load the
project-local MCP configuration.

## What the link proves

Codex does not click editor coordinates or edit project JSON. It discovers the
SAG Video contract, reads stable project and timeline identities, invokes typed
revision-checked commands, and inspects causal receipts. The browser polls the
same canonical project and reflects an external revision within approximately
2.5 seconds.

The project-local `.codex/config.toml` starts `sag_video.mcp_server` over stdio.
It contains no access token. On every tool call the server reads the short-lived
paired token from the ignored `.sag-video/codex-token` file.

## One-time activation

1. Start SAG Video at `http://127.0.0.1:8080`.
2. Start a new Codex session from the `sag-video` repository so Codex loads the
   trusted project `.codex/config.toml`.
3. Open the desired project in the browser and press **Pair**.
4. Give the displayed six-digit code to Codex, or run:

   ```sh
   PYTHONPATH=src python -m sag_video.cli pair 123456 --actor codex \
     --save-token .sag-video/codex-token
   ```

The code is single-use and expires after ten minutes. The stored token expires
after eight hours, is written with mode `0600`, and is never committed. Pair
again when it expires. Because the MCP server reads the file per request, a new
token does not require another Codex restart.

Run the read-only preflight when needed:

```sh
PYTHONPATH=src python scripts/codex_link_preflight.py
```

For an invite-protected instance, preflight should report `actor: codex` and
only the paired project under `visible_projects`.

## First acceptance run

Use a disposable project containing at least two observed-valid clips. Keep the
browser open, then tell Codex:

> Use only the SAG Video MCP tools. Discover the application contract and list
> the projects visible to you. Inspect the current project and selection. Select
> the second video clip, move it directly after the first clip, trim its end by
> one second, set its scale to 0.85 and rotation to 4 degrees, then re-read the
> project to confirm the exact new revision. Start a verified render of that
> revision, poll it to a terminal state, and inspect the causal receipt. Do not
> use browser clicks, DOM automation, raw FFmpeg, or direct database access.

Success requires all of the following:

- Codex sees only the project to which its token is paired.
- The browser shows `codex connected` and reflects each committed revision.
- Every edit is attributed to `codex`, uses the expected revision, and returns
  a causal receipt.
- A stale command fails instead of being silently replayed.
- The render is bound to the confirmed revision.
- Codex reports observed success only after the artifact observer succeeds.
- Refreshing or restarting retains project state, jobs, receipts, and artifact
  identity.

## Authority boundary

Pairing grants access to one project, not every project in the database.
Authenticated identity overrides actor names supplied in request bodies.
Selection supplies semantic context but never grants mutation authority.
Codex cannot invoke arbitrary shell or FFmpeg operations through the MCP server.
