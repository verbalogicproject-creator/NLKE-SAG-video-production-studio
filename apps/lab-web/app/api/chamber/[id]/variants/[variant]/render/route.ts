import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { VerticalVariantSchema } from '@verbalogix/media-contracts';
import { db } from '@/lib/db';
import { resolveBrandContract } from '@/lib/brand-contract';
import { sagEngine } from '@/lib/engine';
import { apiError, jsonSafe } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

export async function POST(request: Request, { params }: { params: Promise<{ id: string; variant: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id, variant: rawVariant } = await params;
    const variant = VerticalVariantSchema.parse(rawVariant);
    const body = await request.json().catch(() => ({}));
    const row = await db.chamberVariant.findFirst({
      where: { chamberRunId: id, variant, chamberRun: { project: { workspaceId } } },
      include: { chamberRun: true },
    });
    if (!row?.engineProjectId || !row.engineRevision) return NextResponse.json({ error: 'draft_not_accepted' }, { status: 409 });
    const workspace = await db.workspace.findUniqueOrThrow({ where: { id: workspaceId } });
    const activeRenders = await db.chamberVariant.count({
      where: { chamberRun: { project: { workspaceId } }, status: { in: ['RENDERING', 'VERIFYING'] } },
    });
    if (process.env.CLOUD_EXECUTION_ENABLED !== 'true' && activeRenders >= workspace.renderConcurrencyLimit) {
      return NextResponse.json({ error: 'render_concurrency_quota_exceeded' }, { status: 409 });
    }
    const startOfDay = new Date();
    startOfDay.setUTCHours(0, 0, 0, 0);
    const daily = await db.quotaLedger.aggregate({
      where: { workspaceId, kind: 'RENDER_DAILY', occurredAt: { gte: startOfDay } }, _sum: { amount: true },
    });
    if (process.env.CLOUD_EXECUTION_ENABLED !== 'true' && (daily._sum.amount ?? 0n) >= BigInt(workspace.dailyRenderLimit)) {
      return NextResponse.json({ error: 'daily_render_quota_exceeded' }, { status: 409 });
    }
    const brand = await resolveBrandContract(workspaceId);
    if (brand.contract_hash !== row.chamberRun.brandContractHash) {
      return NextResponse.json({ error: 'stale_brand_contract', message: 'BrandSkill changed; regenerate drafts before rendering.' }, { status: 409 });
    }
    const revision = Number(body.projectRevision ?? row.engineRevision);
    const requestId = String(body.requestId ?? `chamber-render-${id}-${variant}-${randomUUID()}`);
    if (!Number.isInteger(revision) || revision !== row.engineRevision) {
      return NextResponse.json({ error: 'stale_project_revision', expected: row.engineRevision, received: revision }, { status: 409 });
    }
    if (process.env.CLOUD_EXECUTION_ENABLED === 'true') {
      const jobId = randomUUID();
      const outcome = await db.$transaction(async (tx) => {
        await tx.$executeRaw`SELECT pg_advisory_xact_lock(hashtext(${`sag-render:${workspaceId}`}))`;
        const duplicate = await tx.canonicalJob.findUnique({
          where: { workspaceId_requestId: { workspaceId, requestId } },
        });
        if (duplicate) {
          if (duplicate.kind !== 'RENDER' || duplicate.canonicalEntityId !== row.id) {
            throw Object.assign(new Error('request ID was already used for another mutation'), { status: 409 });
          }
          return { updated: row, jobId: duplicate.id };
        }
        const lockedActive = await tx.chamberVariant.count({
          where: { chamberRun: { project: { workspaceId } }, status: { in: ['RENDERING', 'VERIFYING'] } },
        });
        if (lockedActive >= workspace.renderConcurrencyLimit) {
          throw Object.assign(new Error('render concurrency quota exceeded'), { status: 409 });
        }
        const lockedDaily = await tx.quotaLedger.aggregate({
          where: { workspaceId, kind: 'RENDER_DAILY', occurredAt: { gte: startOfDay } }, _sum: { amount: true },
        });
        if ((lockedDaily._sum.amount ?? 0n) >= BigInt(workspace.dailyRenderLimit)) {
          throw Object.assign(new Error('daily render quota exceeded'), { status: 409 });
        }
        await tx.canonicalJob.create({ data: {
          id: jobId, workspaceId, projectId: row.chamberRun.projectId,
          kind: 'RENDER', state: 'DISPATCH_PENDING', requestId,
          canonicalEntityId: row.id, inputVersion: 'sag-render-job-1',
          inputSnapshot: {
            workspaceId, chamberRunId: id, chamberVariantId: row.id, variant,
            engineProjectId: row.engineProjectId, projectRevision: revision,
            requestId, brandContractHash: brand.contract_hash,
          }, outbox: { create: {} },
        } });
        const changed = await tx.chamberVariant.update({
          where: { id: row.id },
          data: { engineRevision: revision, renderJobId: jobId, status: 'RENDERING' },
        });
        await tx.chamberRun.update({ where: { id }, data: { status: 'RENDERING' } });
        await tx.quotaLedger.create({ data: { workspaceId, kind: 'RENDER_DAILY', amount: 1, requestId, metadata: { chamberRunId: id, variant } } });
        return { updated: changed, jobId };
      });
      return NextResponse.json(jsonSafe({ variant: outcome.updated, receipt: { id: null, payload: { job_id: outcome.jobId } } }), { status: 202 });
    }
    const receipt = await sagEngine.render(workspaceId, row.engineProjectId, revision, requestId);
    const [updated] = await db.$transaction([
      db.chamberVariant.update({
        where: { id: row.id },
        data: { engineRevision: revision, renderJobId: receipt.payload.job_id, receiptId: receipt.id, status: 'RENDERING' },
      }),
      db.chamberRun.update({ where: { id }, data: { status: 'RENDERING' } }),
      db.quotaLedger.create({ data: { workspaceId, kind: 'RENDER_DAILY', amount: 1, requestId, metadata: { chamberRunId: id, variant } } }),
    ]);
    return NextResponse.json(jsonSafe({ variant: updated, receipt }), { status: 202 });
  } catch (error) {
    return apiError(error);
  }
}
