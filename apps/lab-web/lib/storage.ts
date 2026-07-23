import { Storage } from '@google-cloud/storage';

export const MAX_UPLOAD_BYTES = 512 * 1024 * 1024;

export type UploadObject = {
  provider: 'LOCAL' | 'GCS';
  bucket: string | null;
  objectKey: string;
};

export type UploadSessionResult = UploadObject & {
  sessionUri: string;
  expiresAt: Date;
};

export type ObjectMetadata = UploadObject & {
  generation: string;
  sizeBytes: bigint;
  contentType: string;
};

export interface ManagedStorage {
  createUploadSession(input: {
    workspaceId: string;
    projectId: string;
    assetId: string;
    contentType: string;
    sizeBytes: bigint;
    origin?: string;
  }): Promise<UploadSessionResult>;
  inspect(object: UploadObject): Promise<ObjectMetadata>;
  signedDownload(object: UploadObject, expiresInSeconds?: number): Promise<string>;
}

function safeId(value: string): string {
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(value)) throw new Error('invalid storage identity');
  return value;
}

export function uploadObjectKey(workspaceId: string, projectId: string, assetId: string): string {
  return `workspaces/${safeId(workspaceId)}/projects/${safeId(projectId)}/uploads/${safeId(assetId)}`;
}

export function managedBlobUri(assetId: string): string {
  return `sag-blob://${safeId(assetId)}`;
}

export function managedArtifactUri(assetId: string): string {
  return `sag-artifact://${safeId(assetId)}`;
}

class LocalStorage implements ManagedStorage {
  async createUploadSession(input: {
    workspaceId: string;
    projectId: string;
    assetId: string;
    contentType: string;
    sizeBytes: bigint;
  }): Promise<UploadSessionResult> {
    return {
      provider: 'LOCAL',
      bucket: null,
      objectKey: uploadObjectKey(input.workspaceId, input.projectId, input.assetId),
      sessionUri: `/api/projects/${encodeURIComponent(input.projectId)}/assets/upload?uploadSessionId=${encodeURIComponent(input.assetId)}`,
      expiresAt: new Date(Date.now() + 15 * 60_000),
    };
  }

  async inspect(): Promise<ObjectMetadata> {
    throw Object.assign(new Error('local uploads are verified by the SAG intake service'), { status: 409 });
  }

  async signedDownload(object: UploadObject): Promise<string> {
    return `/api/artifacts/${encodeURIComponent(object.objectKey)}/download`;
  }
}

class GcsStorage implements ManagedStorage {
  private readonly client = new Storage();

  constructor(private readonly bucketName: string) {}

  async createUploadSession(input: {
    workspaceId: string;
    projectId: string;
    assetId: string;
    contentType: string;
    sizeBytes: bigint;
    origin?: string;
  }): Promise<UploadSessionResult> {
    const objectKey = uploadObjectKey(input.workspaceId, input.projectId, input.assetId);
    const [sessionUri] = await this.client.bucket(this.bucketName).file(objectKey).createResumableUpload({
      origin: input.origin,
      metadata: {
        contentType: input.contentType,
        metadata: {
          workspaceId: input.workspaceId,
          projectId: input.projectId,
          assetId: input.assetId,
          expectedSizeBytes: input.sizeBytes.toString(),
        },
      },
      preconditionOpts: { ifGenerationMatch: 0 },
    });
    return {
      provider: 'GCS',
      bucket: this.bucketName,
      objectKey,
      sessionUri,
      expiresAt: new Date(Date.now() + 15 * 60_000),
    };
  }

  async inspect(object: UploadObject): Promise<ObjectMetadata> {
    if (object.provider !== 'GCS' || object.bucket !== this.bucketName) throw new Error('storage object belongs to another backend');
    const [metadata] = await this.client.bucket(this.bucketName).file(object.objectKey).getMetadata();
    return {
      ...object,
      generation: String(metadata.generation ?? ''),
      sizeBytes: BigInt(String(metadata.size ?? '0')),
      contentType: String(metadata.contentType ?? 'application/octet-stream'),
    };
  }

  async signedDownload(object: UploadObject, expiresInSeconds = 900): Promise<string> {
    if (object.provider !== 'GCS' || object.bucket !== this.bucketName) throw new Error('storage object belongs to another backend');
    const [url] = await this.client.bucket(this.bucketName).file(object.objectKey).getSignedUrl({
      action: 'read',
      version: 'v4',
      expires: Date.now() + Math.min(expiresInSeconds, 3600) * 1000,
    });
    return url;
  }
}

let singleton: ManagedStorage | undefined;

export function storage(): ManagedStorage {
  if (singleton) return singleton;
  const backend = process.env.STORAGE_BACKEND ?? (process.env.NODE_ENV === 'production' ? 'gcs' : 'local');
  if (backend === 'local') singleton = new LocalStorage();
  else if (backend === 'gcs') {
    if (!process.env.GCS_MEDIA_BUCKET) throw new Error('GCS_MEDIA_BUCKET is required for GCS storage');
    singleton = new GcsStorage(process.env.GCS_MEDIA_BUCKET);
  } else throw new Error(`unsupported STORAGE_BACKEND: ${backend}`);
  return singleton;
}
