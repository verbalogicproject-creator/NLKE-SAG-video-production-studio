import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { sagEngine } from '@/lib/engine';
import { apiError, jsonSafe } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const run = await db.chamberRun.findFirst({ where: { id, project: { workspaceId } }, include: { variants: true } });
    if (!run) return NextResponse.json({ error: 'chamber_run_not_found' }, { status: 404 });
    const jobs = [run.analysisJobId, ...run.variants.map((variant) => variant.renderJobId)].filter((value): value is string => Boolean(value));
    const canonical = await db.canonicalJob.findMany({ where: { id: { in: jobs }, workspaceId } });
    if (canonical.length) {
      await db.canonicalJob.updateMany({
        where: { id: { in: canonical.map((job) => job.id) }, state: { in: ['DISPATCH_PENDING', 'QUEUED', 'CLAIMED', 'RUNNING', 'AWAITING_OBSERVATION'] } },
        data: { cancellationRequested: true },
      });
    }
    const canonicalIds = new Set(canonical.map((job) => job.id));
    await Promise.all(jobs.filter((jobId) => !canonicalIds.has(jobId)).map((jobId) => sagEngine.cancel(workspaceId, jobId).catch(() => null)));
    await db.chamberVariant.updateMany({ where: { chamberRunId: id, status: { in: ['PENDING', 'RENDERING', 'VERIFYING'] } }, data: { status: 'CANCELLED' } });
    const cancelled = await db.chamberRun.update({ where: { id }, data: { status: 'CANCELLED' }, include: { variants: true } });
    return NextResponse.json(jsonSafe({ run: cancelled }));
  } catch (error) {
    return apiError(error);
  }
}
