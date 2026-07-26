import { NextResponse } from 'next/server';
import { z } from 'zod';
import { db } from '@/lib/db';
import { apiError, jsonSafe } from '@/lib/http';
import { managedBlobUri, storage } from '@/lib/storage';
import { requireWorkspace } from '@/lib/workspace';

const RequestSchema = z.object({
  uploadSessionId: z.string().min(1),
  generation: z.string().min(1).optional(),
});

export async function POST(request: Request) {
  try {
    const { workspaceId } = await requireWorkspace();
    const input = RequestSchema.parse(await request.json());
    const upload = await db.uploadSession.findFirst({ where: { id: input.uploadSessionId, workspaceId } });
    if (!upload) return NextResponse.json({ error: 'upload_session_not_found' }, { status: 404 });
    if (upload.status === 'PROMOTED') return NextResponse.json(jsonSafe({ upload }), { status: 200 });
    if (upload.expiresAt <= new Date() || !['ISSUED', 'UPLOADED'].includes(upload.status)) {
      return NextResponse.json({ error: 'upload_session_not_active' }, { status: 409 });
    }
    const provider = (process.env.STORAGE_BACKEND ?? (process.env.NODE_ENV === 'production' ? 'gcs' : 'local')) === 'gcs' ? 'GCS' : 'LOCAL';
    const object = await storage().inspect({ provider, bucket: process.env.GCS_MEDIA_BUCKET ?? null, objectKey: upload.objectKey });
    if (input.generation && input.generation !== object.generation) {
      return NextResponse.json({ error: 'object_generation_mismatch' }, { status: 409 });
    }
    if (object.sizeBytes !== upload.expectedSizeBytes || object.contentType !== upload.expectedMimeType) {
      await db.uploadSession.update({ where: { id: upload.id }, data: { status: 'REJECTED' } });
      return NextResponse.json({ error: 'uploaded_object_mismatch' }, { status: 422 });
    }
    const result = await db.$transaction(async (tx) => {
      const current = await tx.uploadSession.findUnique({ where: { id: upload.id } });
      if (!current || !['ISSUED', 'UPLOADED'].includes(current.status)) throw Object.assign(new Error('upload session changed'), { status: 409 });
      const storageObject = await tx.storageObject.create({ data: {
        provider: object.provider,
        bucket: object.bucket,
        objectKey: object.objectKey,
        generation: object.generation,
        byteSize: object.sizeBytes,
      } });
      const asset = await tx.asset.create({ data: {
        id: current.assetId,
        projectId: current.projectId,
        storageObjectId: storageObject.id,
        kind: 'RAW',
        managedUri: managedBlobUri(current.assetId),
        mimeType: current.expectedMimeType,
        sizeBytes: object.sizeBytes,
        metadata: { originalFilename: current.originalFilename, intakeStatus: 'pending' },
      } });
      const job = await tx.canonicalJob.create({ data: {
        workspaceId,
        projectId: current.projectId,
        kind: 'INTAKE',
        state: 'DISPATCH_PENDING',
        requestId: `intake:${current.id}:${object.generation}`,
        canonicalEntityId: asset.id,
        inputVersion: 'sag-intake-1',
        inputSnapshot: {
          workspaceId, controlProjectId: current.projectId, assetId: asset.id,
          object: { provider: object.provider, bucket: object.bucket, key: object.objectKey, generation: object.generation },
          expectedSizeBytes: object.sizeBytes.toString(), expectedMimeType: current.expectedMimeType,
          originalFilename: current.originalFilename,
        },
        outbox: { create: {} },
      } });
      await tx.uploadSession.update({ where: { id: current.id }, data: {
        status: 'VERIFYING', objectGeneration: object.generation,
      } });
      await tx.quotaLedger.create({ data: {
        workspaceId,
        kind: 'UPLOAD_BYTES',
        amount: object.sizeBytes,
        requestId: current.id,
        metadata: { assetId: asset.id, generation: object.generation },
      } });
      return { asset, job };
    });
    return NextResponse.json(jsonSafe(result), { status: 202 });
  } catch (error) {
    return apiError(error);
  }
}
