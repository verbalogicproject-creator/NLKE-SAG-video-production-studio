import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { z } from 'zod';
import { db } from '@/lib/db';
import { sagEngine } from '@/lib/engine';
import { apiError, jsonSafe } from '@/lib/http';
import { storage } from '@/lib/storage';
import { requireApiKey, requireWorkspace } from '@/lib/workspace';

const Destination = z.object({
  destination: z.enum(['youtube_shorts', 'tiktok', 'instagram_reels', 'download']),
  visibility: z.enum(['private', 'draft', 'manual']).default('private'),
  title: z.string().max(100).optional(),
  description: z.string().max(5000).optional(),
});
const Approve = z.object({
  operation: z.literal('approve'), sequenceId: z.string().min(1), sequenceRevision: z.number().int().positive(),
  artifactAssetIds: z.array(z.string().min(1)).min(1).max(4), destinations: z.array(Destination).min(1).max(4),
  requestId: z.string().min(8).max(120).optional(),
});
const Dispatch = z.object({
  operation: z.literal('dispatch'), approvalId: z.string().min(1), requestId: z.string().min(8).max(120).optional(),
});

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const project = await db.project.findFirst({
      where: { id, workspaceId },
      include: { sequences: { where: { archivedAt: null } } },
    });
    if (!project) return NextResponse.json({ error: 'project_not_found' }, { status: 404 });
    const sequences = await Promise.all(project.sequences.map(async (sequence) => {
      const delivery = await sagEngine.deliveryState(workspaceId, sequence.engineProjectId);
      return {
        ...sequence,
        deliveryProfiles: delivery.delivery_profiles,
        releaseApprovals: delivery.release_approvals,
      };
    }));
    return NextResponse.json(jsonSafe({ sequences }));
  } catch (error) { return apiError(error); }
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const authorization = request.headers.get('authorization');
    const raw = await request.json();
    const { id } = await params;
    if (raw.operation === 'approve') {
      if (authorization?.startsWith('Bearer ')) {
        return NextResponse.json({ error: 'human_browser_approval_required' }, { status: 403 });
      }
      const { workspaceId, userId, role } = await requireWorkspace();
      if (!['OWNER', 'ADMIN', 'EDITOR'].includes(role)) return NextResponse.json({ error: 'editor_required' }, { status: 403 });
      const body = Approve.parse(raw);
      const sequence = await db.studioSequence.findFirst({ where: { id: body.sequenceId, projectId: id, project: { workspaceId } } });
      if (!sequence) return NextResponse.json({ error: 'sequence_not_found' }, { status: 404 });
      if (sequence.currentRevision !== body.sequenceRevision) return NextResponse.json({ error: 'stale_sequence_revision' }, { status: 409 });
      if (body.destinations.some((entry) => entry.destination === 'instagram_reels' && entry.visibility !== 'manual')) {
        return NextResponse.json({ error: 'instagram_requires_manual_release_until_public_promotion' }, { status: 422 });
      }
      const artifacts = await db.asset.findMany({
        where: { id: { in: body.artifactAssetIds }, projectId: id, project: { workspaceId }, kind: 'DELIVERABLE' },
      });
      if (artifacts.length !== body.artifactAssetIds.length || artifacts.some((entry) => !entry.engineAssetId || !entry.sha256 || !entry.verifiedAt)) {
        return NextResponse.json({ error: 'independently_verified_artifacts_required' }, { status: 409 });
      }
      const artifactHashes = artifacts.map((entry) => entry.sha256!).sort();
      const destinations = body.destinations.toSorted((left, right) => left.destination.localeCompare(right.destination));
      const result = await sagEngine.approveRelease(workspaceId, sequence.engineProjectId, {
        request_id: body.requestId ?? `release-approval-${randomUUID()}`,
        project_revision: body.sequenceRevision,
        artifact_hashes: artifactHashes,
        destinations,
        approved_by: userId,
      });
      await db.auditEvent.create({ data: {
        workspaceId, actorId: userId, action: 'release.bundle_approved', targetType: 'release_bundle',
        targetId: String(result.approval.id), requestId: `release-approval:${String(result.approval.id)}`,
        evidence: {
          sequenceRevision: body.sequenceRevision, bundleHash: result.approval.bundle_hash,
          artifactHashes, destinations, engineReceiptId: result.receipt.id,
        },
      } }).catch(() => undefined);
      return NextResponse.json(jsonSafe(result), { status: 201 });
    }

    const principal = authorization?.startsWith('Bearer ')
      ? await requireApiKey(request, ['release:dispatch'])
      : await requireWorkspace();
    const body = Dispatch.parse(raw);
    const project = await db.project.findFirst({
      where: { id, workspaceId: principal.workspaceId },
      include: { sequences: { where: { archivedAt: null } } },
    });
    if (!project) return NextResponse.json({ error: 'project_not_found' }, { status: 404 });
    const candidates = await Promise.all(project.sequences.map(async (sequence) => ({
      sequence,
      delivery: await sagEngine.deliveryState(principal.workspaceId, sequence.engineProjectId),
    })));
    const owner = candidates.find(({ delivery }) => delivery.release_approvals.some((entry) => entry.id === body.approvalId));
    if (!owner) return NextResponse.json({ error: 'release_approval_not_found' }, { status: 404 });
    const actor = 'apiKeyId' in principal ? principal.apiKeyId : principal.userId;
    const result = await sagEngine.dispatchRelease(
      principal.workspaceId, owner.sequence.engineProjectId, body.approvalId,
      body.requestId ?? `release-dispatch-${randomUUID()}`,
    );
    const artifactHashes = z.array(z.string()).parse(result.approval.artifact_hashes);
    const artifacts = await db.asset.findMany({
      where: { projectId: id, sha256: { in: artifactHashes }, verifiedAt: { not: null } }, include: { storageObject: true },
    });
    const downloads = await Promise.all(artifacts.filter((entry) => entry.storageObject).map(async (entry) => ({
      assetId: entry.id, sha256: entry.sha256, url: await storage().signedDownload(entry.storageObject!, 900), expiresInSeconds: 900,
    })));
    await db.auditEvent.create({ data: {
      workspaceId: principal.workspaceId, actorId: 'userId' in principal ? principal.userId : undefined,
      action: 'release.bundle_dispatched', targetType: 'release_bundle', targetId: body.approvalId,
      requestId: body.requestId ?? `release-dispatch:${String(result.receipt.id)}`,
      evidence: {
        engineReceiptId: result.receipt.id, attemptIds: result.attempts.map((entry) => entry.id),
        apiKeyId: 'apiKeyId' in principal ? principal.apiKeyId : undefined,
      },
    } }).catch(() => undefined);
    return NextResponse.json(jsonSafe({ ...result, downloads, actor }), { status: 202 });
  } catch (error) { return apiError(error); }
}
