import { createHash } from 'node:crypto';
import { NextResponse } from 'next/server';
import { z } from 'zod';
import { db } from '@/lib/db';
import { apiError, jsonSafe } from '@/lib/http';
import { requireApiKey, requireWorkspace } from '@/lib/workspace';

const Schema = z.object({ approvalId: z.string().min(1) });

export async function POST(request: Request) {
  try {
    const authorization = request.headers.get('authorization');
    const principal = authorization?.startsWith('Bearer ')
      ? await requireApiKey(request, ['youtube:publish'])
      : await requireWorkspace();
    const { approvalId } = Schema.parse(await request.json());
    const approval = await db.publicationApproval.findFirst({
      where: { id: approvalId, workspaceId: principal.workspaceId },
      include: { artifact: true },
    });
    if (!approval) return NextResponse.json({ error: 'approval_not_found' }, { status: 404 });
    if (approval.visibility !== 'private' || approval.state !== 'ACTIVE' || approval.expiresAt <= new Date()) {
      return NextResponse.json({ error: 'approval_not_active' }, { status: 409 });
    }
    if (!approval.artifact.verifiedAt || approval.artifact.sha256 !== approval.artifactSha256) {
      return NextResponse.json({ error: 'artifact_changed_or_unverified' }, { status: 409 });
    }
    const connection = await db.youTubeConnection.findUnique({ where: { workspaceId: principal.workspaceId } });
    if (!connection || connection.channelId !== approval.channelId) {
      return NextResponse.json({ error: 'youtube_channel_changed' }, { status: 409 });
    }
    const idempotencyKey = createHash('sha256')
      .update(`${approval.id}\0${approval.artifactSha256}\0${approval.channelId}\0private`)
      .digest('hex');
    const previous = await db.publicationAttempt.findUnique({ where: { idempotencyKey } });
    if (previous) return NextResponse.json(jsonSafe({ attempt: previous }), { status: previous.state === 'PUBLISHED' ? 200 : 202 });
    const result = await db.$transaction(async (tx) => {
      const attempt = await tx.publicationAttempt.create({ data: {
        workspaceId: principal.workspaceId, approvalId: approval.id, idempotencyKey,
      } });
      const job = await tx.canonicalJob.create({ data: {
        workspaceId: principal.workspaceId,
        projectId: approval.artifact.projectId,
        kind: 'PUBLISH_YOUTUBE',
        state: 'DISPATCH_PENDING',
        requestId: `publish:${idempotencyKey}`,
        canonicalEntityId: attempt.id,
        outbox: { create: {} },
      } });
      await tx.publicationApproval.update({ where: { id: approval.id }, data: { state: 'CONSUMED', consumedAt: new Date() } });
      return { attempt, job };
    });
    return NextResponse.json(jsonSafe(result), { status: 202 });
  } catch (error) { return apiError(error); }
}
