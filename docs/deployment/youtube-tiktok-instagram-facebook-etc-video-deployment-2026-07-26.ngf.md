---
id: youtube-tiktok-instagram-facebook-etc-video-deployment-2026-07-26
kind: deployment_roadmap
format: ngf/0.0.1
status: planned-not-wired
owner_area: sag-video
title: Multi-platform video deployment, credentials, review, and verification
written: 2026-07-26
last_verified: 2026-07-26
---

# Multi-platform video deployment source of truth

This document is an implementation roadmap, not an authorization to publish.
The current milestone ends at independently verified downloadable exports. No
editing, generation, rendering, review, or export operation may depend on a
social account connection.

No credential value belongs in this file, source control, a receipt, runtime
telemetry, an error message, or a browser response.

## Current implementation status

| Capability | Status | Current boundary |
| --- | --- | --- |
| Verified download | implemented foundation | Universal fallback; keep available for every platform |
| YouTube private upload | partial, not acceptance-ready | OAuth, approval, and publish routes exist; complete end-to-end post verification before enabling release |
| TikTok upload to inbox | not wired | Add after verified export; request `video.upload` only when the workflow is ready |
| TikTok direct post | not wired | Requires `video.publish`, platform audit, and a separate human release gate |
| Instagram Reels | not wired | Use the shared Meta connection layer with an Instagram professional-account destination |
| Facebook Page Reels | not wired | Use the shared Meta connection layer with a distinct Page destination |
| LinkedIn video | not wired | Use the provider-neutral publisher adapter and current versioned API headers |
| X video | not wired | Use chunked media upload, processing verification, then post creation |

`planned-not-wired` means account setup may be prepared, but no adapter is
allowed to make editing or export conditional on those credentials.

## Configuration inventory

### Existing common production variables

- `DATABASE_URL`
- `NEXTAUTH_URL`
- `NEXTAUTH_SECRET`
- `SAG_ENGINE_URL`
- `SAG_VIDEO_SERVICE_TOKEN`
- `SAG_DISPATCH_SECRET`

### Google Cloud runtime variables

- `GOOGLE_CLOUD_PROJECT`
- `GCP_REGION`
- `GCS_MEDIA_BUCKET`
- `CLOUD_TASKS_QUEUE`
- `CLOUD_RUN_PUBLISH_JOB`
- `GOOGLE_APPLICATION_CREDENTIALS` for local ADC compatibility only

### Generative-media variables

- `GEMINI_API_KEY`
- `SAG_GOOGLE_GENAI_BACKEND`
- `GOOGLE_GENAI_LOCATION`

### Connection encryption

- `SAG_CONNECTIONS_KMS_KEY`
- `YOUTUBE_KMS_KEY` as the current compatibility fallback only

The KMS variable contains a full CryptoKey resource name. It does not contain
service-account JSON, raw key material, or ciphertext. Cloud Run uses
Application Default Credentials and a service account with the least-privilege
Cloud KMS encrypt/decrypt permissions for that key. OAuth client secrets belong
in Secret Manager. Cloud KMS retains the key; the application database retains
only ciphertext and non-secret routing metadata. See the official
[Cloud KMS encryption guidance](https://docs.cloud.google.com/kms/docs/encrypt-decrypt).

Workspace OAuth tokens are encrypted before database storage. Encryption uses
workspace ID, connection ID, provider, and account identity as additional
authenticated context so ciphertext cannot be moved between accounts without
detection. Token plaintext must exist only for the bounded adapter call.

### YouTube adapter variables

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `YOUTUBE_OAUTH_REDIRECT_URI`

YouTube modifications require user OAuth. A service-account JSON file can
authorize Google Cloud and supported generative services locally, but it cannot
replace ordinary YouTube channel authorization. The YouTube Data API service
account flow applies only to supported content-owner cases. Use the web-server
OAuth flow, exact redirect URI matching, CSRF state validation, offline access,
and encrypted refresh-token storage. See [YouTube OAuth for web server
applications](https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps)
and [YouTube authentication guidance](https://developers.google.com/youtube/v3/guides/authentication).

### Proposed TikTok adapter variables

- `TIKTOK_CLIENT_KEY`
- `TIKTOK_CLIENT_SECRET`
- `TIKTOK_OAUTH_REDIRECT_URI`

Start with upload-to-inbox using `video.upload`. Direct Post requires
`video.publish`, user authorization, compliance with creator-information and
posting requirements, and platform audit before public visibility. Unaudited
clients are restricted. See the [TikTok Content Posting API](https://developers.tiktok.com/doc/content-posting-api-get-started/)
and [upload-video reference](https://developers.tiktok.com/doc/content-posting-api-reference-upload-video).

### Proposed Meta adapter variables

- `META_APP_ID`
- `META_APP_SECRET`
- `META_OAUTH_REDIRECT_URI`
- `META_WEBHOOK_VERIFY_TOKEN`

One encrypted workspace connection may discover both Facebook Pages and linked
Instagram professional accounts, but each destination retains its own stable
identity, granted capabilities, release decision, and verification result.
Use the current official [Instagram content-publishing
documentation](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing/)
and [Facebook Reels publishing
guide](https://developers.facebook.com/docs/video-api/guides/reels-publishing/)
when implementation begins.

### Proposed LinkedIn adapter variables

- `LINKEDIN_CLIENT_ID`
- `LINKEDIN_CLIENT_SECRET`
- `LINKEDIN_OAUTH_REDIRECT_URI`

LinkedIn publication must resolve the authorized owner, initialize the video
upload for that owner, complete upload, verify processing, and reference the
result from the post. Send the currently supported `Linkedin-Version` and
Rest.li protocol headers. Do not freeze a version in the database. See the
[LinkedIn Videos API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/videos-api).

### Proposed X adapter variables

- `X_CLIENT_ID`
- `X_CLIENT_SECRET`
- `X_OAUTH_REDIRECT_URI`

Video publication uses INIT, APPEND, FINALIZE, and STATUS where required, then
creates a post with the verified `media_id`. See [X chunked media
upload](https://docs.x.com/x-api/media/quickstart/media-upload-chunked).

## Encrypted per-workspace connection data

The following belong to engine-authorized encrypted workspace connection
records, not environment variables:

- YouTube channel IDs.
- Facebook Page IDs.
- Instagram professional-account IDs.
- LinkedIn member or organization owner URNs.
- X user IDs.
- Access tokens and refresh tokens.
- Granted scopes and denied scopes.
- Token issue and expiry timestamps.
- Provider account display metadata.
- Provider review or audit status.
- Last successful identity verification.

Prisma may mirror workspace identity, connection display state, and dispatch
routing. It must not become a second editing, artifact, approval, or publication
authority. Protected token plaintext never enters Prisma logs or browser JSON.

## Console setup and review actions

### Google and YouTube

1. Enable the YouTube Data API in the production Google Cloud project.
2. Configure the OAuth consent screen and the minimum required YouTube scope.
3. Create a Web application OAuth client and register the exact HTTPS callback.
4. Store the client secret in Secret Manager and bind it to Cloud Run.
5. Complete any Google verification required for the requested scope and user type.
6. Test private upload, processing completion, metadata readback, and hash-bound receipt reconciliation on a non-public channel asset.

### TikTok

1. Register the application and Content Posting product.
2. Register the exact HTTPS redirect URI and content-posting scopes.
3. Complete upload-to-inbox testing with a test account.
4. Submit the direct-post integration for audit before enabling public visibility.
5. Keep `video.upload` and `video.publish` as distinct adapter capabilities.

### Meta

1. Create or select the Meta app and configure Facebook Login for Business.
2. Register the exact OAuth callback and webhook verify configuration.
3. Connect test Pages and linked Instagram professional accounts.
4. Request only the permissions used by the Page and Instagram publishing flows.
5. Complete App Review and business verification where Meta requires them.
6. Verify container creation, processing, publish, destination identity, and post readback separately for Facebook and Instagram.

### LinkedIn and X

1. Enable the required LinkedIn products and request organization permissions only when organization publishing is implemented.
2. Verify current LinkedIn version support before every adapter release.
3. Configure the X OAuth client and media/post permissions.
4. Test X chunk finalization and processing status before post creation.
5. Record rate-limit, processing, and platform-policy failures as classified publication attempts.

## Verification commands that do not print secrets

Report presence only:

```sh
node -e 'const names=["DATABASE_URL","NEXTAUTH_URL","NEXTAUTH_SECRET","SAG_ENGINE_URL","SAG_VIDEO_SERVICE_TOKEN","SAG_DISPATCH_SECRET","GOOGLE_CLOUD_PROJECT","GCP_REGION","GCS_MEDIA_BUCKET","CLOUD_TASKS_QUEUE","CLOUD_RUN_PUBLISH_JOB","SAG_CONNECTIONS_KMS_KEY","GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET","YOUTUBE_OAUTH_REDIRECT_URI","TIKTOK_CLIENT_KEY","TIKTOK_CLIENT_SECRET","TIKTOK_OAUTH_REDIRECT_URI","META_APP_ID","META_APP_SECRET","META_OAUTH_REDIRECT_URI","META_WEBHOOK_VERIFY_TOKEN","LINKEDIN_CLIENT_ID","LINKEDIN_CLIENT_SECRET","LINKEDIN_OAUTH_REDIRECT_URI","X_CLIENT_ID","X_CLIENT_SECRET","X_OAUTH_REDIRECT_URI"]; for(const name of names) console.log(`${name}: ${process.env[name]?"set":"missing"}`)'
```

Verify the active Cloud Run identity without exporting a key:

```sh
gcloud run services describe sag-video-web --region REGION --format='value(spec.template.spec.serviceAccountName)'
```

Verify KMS IAM binding names and roles without decrypting anything:

```sh
gcloud kms keys get-iam-policy CONNECTIONS_KEY --keyring CONNECTIONS_KEYRING --location REGION --format='table(bindings.role,bindings.members)'
```

Verify database connection metadata without selecting encrypted payloads:

```sql
SELECT provider, purpose, display_name, state, secret_fingerprint, updated_at
FROM provider_connections
ORDER BY updated_at DESC;
```

Never use `env`, `printenv`, Secret Manager value output, decrypted token output,
or verbose HTTP tracing in acceptance evidence.

## Adapter contract and release invariants

Every publisher adapter must implement prepare, validate, dispatch, poll,
verify, and reconcile. A dispatch request is idempotent on destination,
artifact SHA-256, metadata revision, and human approval receipt. A provider ID
is never success by itself.

Every public release must remain:

- Explicitly human-approved.
- Bound to fixed master and variant revisions.
- Bound to independently verified artifact hashes.
- Idempotent across retries and reconnects.
- Verified by provider readback after processing.
- Reversible or privacy-restricted where the platform permits.
- Recorded without secret values.

## Roadmap order

1. Preserve verified download as the universal fallback.
2. Finish private YouTube publication and post-publication verification.
3. Add TikTok upload-to-inbox, then direct post only after audit and approval.
4. Add Instagram Reels and Facebook Page Reels through the shared Meta layer.
5. Add LinkedIn and X through the same provider-neutral adapter contract.
6. Keep every public release human-approved, artifact-hash-bound, idempotent, and independently verified.

No public publication is part of the current SAG Video acceptance production.
