# Invite-only proof deployment

The repository includes a split control/observer Docker Compose deployment.
Both containers mount the artifact volume, but only the control service invokes
FFmpeg and only the observer service evaluates the completed file.

```sh
SAG_VIDEO_INVITE_TOKEN='a-long-random-invite' docker compose -f deploy/compose.yml up --build
```

The proof uses SQLite and a shared filesystem intentionally. That is adequate
for one invite-only instance but not horizontally scalable. A public or
multi-instance deployment must replace these adapters with PostgreSQL and
private object storage before enabling general uploads.

Required production controls:

- Place both services behind HTTPS.
- Expose only the control service publicly.
- Restrict the observer service to authenticated internal traffic.
- Store the invite secret outside the image.
- Put persistent database and artifact volumes on encrypted storage.
- Apply CPU, memory, request-size, render-concurrency, and artifact-retention
  limits at the platform boundary.
- Use separate Cloud Run services or equivalent and set
  `SAG_VIDEO_OBSERVER_MODE=separate_service`.

Google OAuth allowlisting, signed object-storage uploads, PostgreSQL, render
queues, billing, and multi-tenant isolation remain productionization work; the
implemented invite token and pairing flow provide the bounded proof access.

