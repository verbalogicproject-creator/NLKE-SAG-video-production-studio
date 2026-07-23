import { Readable } from 'node:stream';
import { Storage } from '@google-cloud/storage';
import { PrismaClient } from '@prisma/client';
import { PrismaPg } from '@prisma/adapter-pg';
import { GoogleAuth } from 'google-auth-library';
import { google, type youtube_v3 } from 'googleapis';

const db = new PrismaClient({ adapter: new PrismaPg({ connectionString: required('DATABASE_URL') }) });
const storage = new Storage();
const cloudAuth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

async function kms(operation: 'encrypt' | 'decrypt', value: string, aad: string): Promise<string> {
  const client = await cloudAuth.getClient();
  const field = operation === 'encrypt' ? 'plaintext' : 'ciphertext';
  const response = await client.request<Record<string, string>>({
    url: `https://cloudkms.googleapis.com/v1/${required('YOUTUBE_KMS_KEY')}:${operation}`,
    method: 'POST',
    data: {
      [field]: operation === 'encrypt' ? Buffer.from(value, 'utf8').toString('base64') : value,
      additionalAuthenticatedData: Buffer.from(aad, 'utf8').toString('base64'),
    },
  });
  const result = response.data[operation === 'encrypt' ? 'ciphertext' : 'plaintext'];
  if (!result) throw new Error(`KMS ${operation} returned no value`);
  return operation === 'decrypt' ? Buffer.from(result, 'base64').toString('utf8') : result;
}

async function findExisting(youtube: youtube_v3.Youtube, channelId: string, approvalId: string): Promise<string | undefined> {
  const channels = await youtube.channels.list({ part: ['contentDetails'], id: [channelId] });
  const uploads = channels.data.items?.[0]?.contentDetails?.relatedPlaylists?.uploads;
  if (!uploads) return undefined;
  const items = await youtube.playlistItems.list({ part: ['contentDetails'], playlistId: uploads, maxResults: 50 });
  const ids = (items.data.items ?? []).map((item) => item.contentDetails?.videoId).filter((id): id is string => Boolean(id));
  if (!ids.length) return undefined;
  const videos = await youtube.videos.list({ part: ['snippet', 'status'], id: ids });
  return videos.data.items?.find((video) =>
    video.status?.privacyStatus === 'private' && video.snippet?.description?.includes(`sag-approval:${approvalId}`),
  )?.id ?? undefined;
}

async function mediaBody(artifact: {
  engineAssetId: string | null;
  storageObject: { provider: 'LOCAL' | 'GCS'; bucket: string | null; objectKey: string } | null;
}, workspaceId: string): Promise<Readable> {
  if (artifact.storageObject?.provider === 'GCS' && artifact.storageObject.bucket) {
    return storage.bucket(artifact.storageObject.bucket).file(artifact.storageObject.objectKey).createReadStream();
  }
  if (!artifact.engineAssetId) throw new Error('artifact has no readable storage object');
  const response = await fetch(`${required('SAG_ENGINE_URL').replace(/\/$/, '')}/api/artifacts/${artifact.engineAssetId}/content`, {
    headers: { 'x-sag-workspace-id': workspaceId, 'x-sag-service-token': required('SAG_VIDEO_SERVICE_TOKEN') },
  });
  if (!response.ok || !response.body) throw new Error(`engine artifact download failed with ${response.status}`);
  return Readable.fromWeb(response.body as never);
}

async function publish(canonicalJobId: string): Promise<void> {
  const claimed = await db.canonicalJob.updateMany({
    where: { id: canonicalJobId, kind: 'PUBLISH_YOUTUBE', state: 'CLAIMED' },
    data: { state: 'RUNNING', leaseExpiresAt: new Date(Date.now() + 60 * 60_000) },
  });
  if (!claimed.count) return;
  const job = await db.canonicalJob.findUniqueOrThrow({ where: { id: canonicalJobId } });
  const attempt = await db.publicationAttempt.findFirstOrThrow({
    where: { id: job.canonicalEntityId, workspaceId: job.workspaceId },
    include: { approval: { include: { artifact: { include: { storageObject: true, project: true } } } }, workspace: { include: { youtubeConnection: true } } },
  });
  const connection = attempt.workspace.youtubeConnection;
  if (!connection || connection.channelId !== attempt.approval.channelId) throw new Error('approved YouTube channel is no longer connected');
  if (attempt.approval.visibility !== 'private' || !attempt.approval.artifact.verifiedAt || attempt.approval.artifact.sha256 !== attempt.approval.artifactSha256) {
    throw new Error('publication approval is not bound to the current verified artifact');
  }
  const aad = `youtube:${job.workspaceId}:${connection.channelId}`;
  const oauth = new google.auth.OAuth2(required('GOOGLE_CLIENT_ID'), required('GOOGLE_CLIENT_SECRET'));
  oauth.setCredentials({
    access_token: await kms('decrypt', connection.encryptedAccessToken, aad),
    refresh_token: connection.encryptedRefreshToken ? await kms('decrypt', connection.encryptedRefreshToken, aad) : undefined,
    expiry_date: connection.expiresAt?.getTime(),
  });
  oauth.on('tokens', async (tokens) => {
    await db.youTubeConnection.update({ where: { id: connection.id }, data: {
      encryptedAccessToken: tokens.access_token ? await kms('encrypt', tokens.access_token, aad) : undefined,
      encryptedRefreshToken: tokens.refresh_token ? await kms('encrypt', tokens.refresh_token, aad) : undefined,
      expiresAt: tokens.expiry_date ? new Date(tokens.expiry_date) : undefined,
    } });
  });
  const youtube = google.youtube({ version: 'v3', auth: oauth });
  if (attempt.state === 'AMBIGUOUS' || attempt.state === 'UPLOADING') {
    const existing = await findExisting(youtube, connection.channelId, attempt.approval.id);
    if (existing) {
      await complete(job.id, attempt.id, existing);
      return;
    }
  }
  await db.publicationAttempt.update({ where: { id: attempt.id }, data: { state: 'UPLOADING', attempt: { increment: 1 } } });
  try {
    const response = await youtube.videos.insert({
      part: ['snippet', 'status'],
      requestBody: {
        snippet: {
          title: attempt.approval.artifact.project.name.slice(0, 100),
          description: `Created with SAG Video\n\nsag-approval:${attempt.approval.id}`,
        },
        status: { privacyStatus: 'private', selfDeclaredMadeForKids: false },
      },
      media: { mimeType: attempt.approval.artifact.mimeType ?? 'video/mp4', body: await mediaBody(attempt.approval.artifact, job.workspaceId) },
    });
    if (!response.data.id) throw new Error('YouTube upload returned no video id');
    await complete(job.id, attempt.id, response.data.id);
  } catch (error) {
    const status = Number((error as { response?: { status?: number } }).response?.status ?? 0);
    const deterministic = status >= 400 && status < 500 && ![408, 409, 429].includes(status);
    await db.$transaction([
      db.publicationAttempt.update({ where: { id: attempt.id }, data: {
        state: deterministic ? 'FAILED' : 'AMBIGUOUS', boundedError: String(error).slice(0, 2000),
      } }),
      db.canonicalJob.update({ where: { id: job.id }, data: {
        state: deterministic ? 'FAILED' : 'INTERRUPTED', errorCode: deterministic ? 'youtube_rejected' : 'youtube_ambiguous', errorDetail: String(error).slice(0, 2000),
      } }),
    ]);
    throw error;
  }
}

async function complete(jobId: string, attemptId: string, videoId: string): Promise<void> {
  const job = await db.canonicalJob.findUniqueOrThrow({ where: { id: jobId } });
  await db.$transaction([
    db.publicationAttempt.update({ where: { id: attemptId }, data: { state: 'PUBLISHED', youtubeVideoId: videoId, boundedError: null } }),
    db.canonicalJob.update({ where: { id: jobId }, data: { state: 'SUCCEEDED', leaseExpiresAt: null } }),
    db.auditEvent.create({ data: {
      workspaceId: job.workspaceId, action: 'youtube.published_private', targetType: 'youtube_video', targetId: videoId,
      requestId: `published:${attemptId}`, evidence: { attemptId, privacyStatus: 'private' },
    } }),
  ]);
}

const canonicalJobId = required('SAG_CANONICAL_JOB_ID');
publish(canonicalJobId)
  .catch(async (error) => {
    await db.canonicalJob.updateMany({
      where: { id: canonicalJobId, state: 'RUNNING' },
      data: { state: 'FAILED', errorCode: 'publisher_failed', errorDetail: String(error).slice(0, 2000) },
    }).catch(() => undefined);
    console.error(error);
    process.exitCode = 1;
  })
  .finally(() => db.$disconnect());
