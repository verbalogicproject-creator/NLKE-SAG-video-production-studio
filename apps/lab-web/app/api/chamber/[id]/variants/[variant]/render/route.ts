import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { VerticalVariantSchema } from '@verbalogix/media-contracts';
import { db } from '@/lib/db';
import { resolveBrandContract } from '@/lib/brand-contract';
import { sagEngine } from '@/lib/engine';
import { apiError, jsonSafe } from '@/lib/http';
import { enqueue, Queues } from '@/lib/queue';
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
    const brand = await resolveBrandContract(workspaceId);
    if (brand.contract_hash !== row.chamberRun.brandContractHash) {
      return NextResponse.json({ error: 'stale_brand_contract', message: 'BrandSkill changed; regenerate drafts before rendering.' }, { status: 409 });
    }
    const revision = Number(body.projectRevision ?? row.engineRevision);
    const receipt = await sagEngine.render(workspaceId, row.engineProjectId, revision, `chamber-render-${id}-${variant}-${randomUUID()}`);
    const updated = await db.chamberVariant.update({
      where: { id: row.id },
      data: { engineRevision: revision, renderJobId: receipt.payload.job_id, receiptId: receipt.id, status: 'RENDERING' },
    });
    await db.chamberRun.update({ where: { id }, data: { status: 'RENDERING' } });
    await enqueue(Queues.CHAMBER_SYNC, { runId: id });
    return NextResponse.json(jsonSafe({ variant: updated, receipt }), { status: 202 });
  } catch (error) {
    return apiError(error);
  }
}
