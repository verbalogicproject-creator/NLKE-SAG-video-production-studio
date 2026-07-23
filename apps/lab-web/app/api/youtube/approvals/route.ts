import { NextResponse } from 'next/server';
import { z } from 'zod';
import { db } from '@/lib/db';
import { apiError, jsonSafe } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

const Schema = z.object({ artifactAssetId: z.string().min(1) });

export async function POST(request: Request) {
  try {
    const { workspaceId, userId, role } = await requireWorkspace();
    if (!['OWNER', 'ADMIN', 'EDITOR'].includes(role)) return NextResponse.json({ error: 'editor_required' }, { status: 403 });
    const { artifactAssetId } = Schema.parse(await request.json());
    const [artifact, connection] = await Promise.all([
      db.asset.findFirst({ where: { id: artifactAssetId, project: { workspaceId }, kind: 'DELIVERABLE' } }),
      db.youTubeConnection.findUnique({ where: { workspaceId } }),
    ]);
    if (!artifact?.sha256 || !artifact.verifiedAt) return NextResponse.json({ error: 'verified_artifact_required' }, { status: 409 });
    if (!connection) return NextResponse.json({ error: 'youtube_not_connected' }, { status: 409 });
    const existing = await db.publicationApproval.findFirst({ where: {
      workspaceId, artifactSha256: artifact.sha256, channelId: connection.channelId,
      state: 'ACTIVE', expiresAt: { gt: new Date() },
    } });
    if (existing) return NextResponse.json(jsonSafe({ approval: existing }));
    const approval = await db.publicationApproval.create({ data: {
      workspaceId,
      artifactAssetId: artifact.id,
      artifactSha256: artifact.sha256,
      channelId: connection.channelId,
      visibility: 'private',
      approvedById: userId,
      expiresAt: new Date(Date.now() + 10 * 60_000),
    } });
    await db.auditEvent.create({ data: {
      workspaceId, actorId: userId, action: 'youtube.publication_approved',
      targetType: 'publication_approval', targetId: approval.id,
      requestId: `approval:${approval.id}`,
      evidence: { artifactSha256: artifact.sha256, channelId: connection.channelId, visibility: 'private' },
    } });
    return NextResponse.json(jsonSafe({ approval }), { status: 201 });
  } catch (error) { return apiError(error); }
}
