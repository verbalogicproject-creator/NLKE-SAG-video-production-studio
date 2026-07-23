import { S3Client, PutObjectCommand, GetObjectCommand } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';

/**
 * Cloudflare R2 is S3-compatible. We only ever talk to R2 through the
 * S3 SDK using the account's R2 credentials. Browsers get presigned URLs
 * and upload directly — the Next.js server never proxies bytes.
 */

export const r2 = new S3Client({
  region: 'auto',
  endpoint: `https://${process.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId:     process.env.R2_ACCESS_KEY_ID     ?? '',
    secretAccessKey: process.env.R2_SECRET_ACCESS_KEY ?? '',
  },
});

export const Buckets = {
  masters:      process.env.R2_BUCKET_MASTERS      ?? 'verbalogix-lab-masters',
  deliverables: process.env.R2_BUCKET_DELIVERABLES ?? 'verbalogix-lab-deliverables',
} as const;

/** Issue a presigned PUT URL so the browser can upload directly to R2. */
export async function presignUpload(params: {
  bucket: keyof typeof Buckets;
  key: string;
  contentType: string;
  /** seconds until URL expires; default 900 (15 min) — plan acceptance criterion */
  expiresIn?: number;
}): Promise<{ url: string; expiresAt: Date }> {
  const cmd = new PutObjectCommand({
    Bucket: Buckets[params.bucket],
    Key: params.key,
    ContentType: params.contentType,
  });
  const expiresIn = params.expiresIn ?? 900;
  const url = await getSignedUrl(r2, cmd, { expiresIn });
  return { url, expiresAt: new Date(Date.now() + expiresIn * 1000) };
}

/** Issue a presigned GET URL so clients can download a deliverable. */
export async function presignDownload(params: {
  bucket: keyof typeof Buckets;
  key: string;
  expiresIn?: number;
}): Promise<{ url: string }> {
  const cmd = new GetObjectCommand({
    Bucket: Buckets[params.bucket],
    Key: params.key,
  });
  const url = await getSignedUrl(r2, cmd, { expiresIn: params.expiresIn ?? 900 });
  return { url };
}

/** Helper: build an R2 key for an asset of a project */
export function assetKey(opts: {
  workspaceId: string;
  projectId: string;
  assetId: string;
  extension: string;
}): string {
  return `w/${opts.workspaceId}/p/${opts.projectId}/a/${opts.assetId}.${opts.extension}`;
}
