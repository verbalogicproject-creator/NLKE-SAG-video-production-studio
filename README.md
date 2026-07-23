# Verbalogix Chamber

Verbalogix Chamber is a Termux-capable, agent-native short-video production monorepo. The Verbalogix Next.js application owns users, workspaces, brand rules, and production workflow; the SAG Python engine owns canonical revisioned edits, source-backed analysis, FFmpeg rendering, and independent output verification.

## First milestone

One upload produces distinct, editable drafts for YouTube Shorts, TikTok, and Instagram Reels. Captions are tied to exact transcript word IDs. Accepted drafts become revisioned SAG projects, and a deliverable is not ready until its encoded output passes observation.

```text
Upload → Analyze → Drafts → Review/Edit → Render → Verify → Ready to publish
```

The production beta targets GCP and supports private YouTube publishing only. Long-form output, billing, Remotion, and other social publishers are intentionally unsupported.

## Layout

- `apps/lab-web` — user-facing Next.js Chamber
- `services/sag-engine` — FastAPI analysis/editor/render service
- `deploy/terraform` - GCP infrastructure and Cloud Run job definitions
- `packages/media-contracts` — versioned cross-runtime contracts
- `packages/lab-sdk` - REST and MCP SDK types
- `workers/cloud-jobs` - private YouTube publication worker
- `prisma` — Verbalogix control-plane schema

## Termux development

Copy `.env.example` to `.env.local`, configure either remote word-timestamp transcription or whisper.cpp, then run:

```sh
npm install -g pnpm@9.12.0
pnpm install
make preflight
sh scripts/dev-termux.sh
```

Open `http://127.0.0.1:3000/dashboard`. Local mode creates an isolated development user and workspace; it must never be enabled in a public deployment.

## Verification

```sh
make test
make contracts
pnpm typecheck
```

The original SAG engine documentation is retained in `services/sag-engine/README.md`.
