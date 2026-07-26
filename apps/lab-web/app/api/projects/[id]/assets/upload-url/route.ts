import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { z } from 'zod';
import { db } from '@/lib/db';
import { apiError, jsonSafe } from '@/lib/http';
import { MAX_UPLOAD_BYTES, storage } from '@/lib/storage';
import { requireWorkspace } from '@/lib/workspace';

const RequestSchema = z.object({
  filename: z.string().trim().min(1).max(180),
  contentType: z.string().regex(/^(video|audio)\/[A-Za-z0-9.+-]+$/),
  sizeBytes: z.coerce.bigint().positive().max(BigInt(MAX_UPLOAD_BYTES)),
});

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id: projectId } = await params;
    const input = RequestSchema.parse(await request.json());
    const workspace = await db.workspace.findUnique({ where: { id: workspaceId } });
    const project = await db.project.findFirst({ where: { id: projectId, workspaceId } });
    if (!workspace || !project) return NextResponse.json({ error: 'project_not_found' }, { status: 404 });
    if (input.sizeBytes > workspace.uploadLimitBytes) {
      return NextResponse.json({ error: 'upload_quota_exceeded' }, { status: 413 });
    }
    const [stored, reserved] = await Promise.all([
      db.quotaLedger.aggregate({ where: { workspaceId, kind: 'STORAGE_BYTES' }, _sum: { amount: true } }),
      db.uploadSession.aggregate({
        where: { workspaceId, status: { in: ['ISSUED', 'UPLOADED', 'VERIFYING'] }, expiresAt: { gt: new Date() } },
        _sum: { expectedSizeBytes: true },
      }),
    ]);
    if ((stored._sum.amount ?? 0n) + (reserved._sum.expectedSizeBytes ?? 0n) + input.sizeBytes > workspace.storageLimitBytes) {
      return NextResponse.json({ error: 'workspace_storage_quota_exceeded' }, { status: 409 });
    }
    const assetId = `asset_${randomUUID().replaceAll('-', '')}`;
    const issued = await storage().createUploadSession({
      workspaceId,
      projectId,
      assetId,
      contentType: input.contentType,
      sizeBytes: input.sizeBytes,
      origin: new URL(request.url).origin,
    });
    const upload = await db.uploadSession.create({
      data: {
        id: `upload_${randomUUID().replaceAll('-', '')}`,
        workspaceId,
        projectId,
        assetId,
        objectKey: issued.objectKey,
        originalFilename: input.filename,
        expectedSizeBytes: input.sizeBytes,
        expectedMimeType: input.contentType,
        expiresAt: issued.expiresAt,
      },
    });
    return NextResponse.json(jsonSafe({
      uploadSessionId: upload.id,
      assetId,
      sessionUri: issued.sessionUri,
      expiresAt: issued.expiresAt,
    }), { status: 201 });
  } catch (error) {
    return apiError(error);
  }
}
