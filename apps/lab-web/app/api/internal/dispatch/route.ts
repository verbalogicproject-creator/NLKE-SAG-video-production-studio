import { NextResponse } from 'next/server';
import { z } from 'zod';
import { db } from '@/lib/db';
import { startCloudRunJob } from '@/lib/cloud-dispatch';
import { apiError } from '@/lib/http';

const BodySchema = z.object({ canonicalJobId: z.string().min(1) });

function isAuthorized(request: Request): boolean {
  if (process.env.NODE_ENV !== 'production') return request.headers.get('x-sag-dispatch-secret') === process.env.SAG_DISPATCH_SECRET;
  return Boolean(request.headers.get('x-cloudtasks-taskname'));
}

export async function POST(request: Request) {
  try {
    if (!isAuthorized(request)) return NextResponse.json({ error: 'forbidden' }, { status: 403 });
    const { canonicalJobId } = BodySchema.parse(await request.json());
    if (process.env.CLOUD_EXECUTION_ENABLED !== 'true') {
      return NextResponse.json({ error: 'cloud_execution_disabled' }, { status: 503 });
    }
    const outcome = await db.$transaction(async (tx) => {
      await tx.$executeRaw`SELECT pg_advisory_xact_lock(hashtext('sag-heavy-dispatch'))`;
      const pending = await tx.canonicalJob.findUnique({ where: { id: canonicalJobId }, select: { kind: true } });
      if (!pending) return 'missing' as const;
      if (['ANALYSIS', 'RENDER'].includes(pending.kind)) {
        const activeHeavy = await tx.canonicalJob.count({
          where: { kind: { in: ['ANALYSIS', 'RENDER'] }, state: { in: ['CLAIMED', 'RUNNING'] } },
        });
        if (activeHeavy >= Number(process.env.GLOBAL_HEAVY_JOB_LIMIT ?? '2')) return 'saturated' as const;
      }
      const claimed = await tx.canonicalJob.updateMany({
        where: {
          id: canonicalJobId,
          OR: [
            { state: { in: ['QUEUED', 'DISPATCH_PENDING', 'INTERRUPTED'] } },
            { state: 'CLAIMED', leaseExpiresAt: { lt: new Date() } },
          ],
        },
        data: {
          state: 'CLAIMED',
          claimedBy: request.headers.get('x-cloudtasks-taskname') ?? 'local-dispatch',
          claimedAt: new Date(),
          leaseExpiresAt: new Date(Date.now() + 15 * 60_000),
          attempt: { increment: 1 },
        },
      });
      return claimed.count ? 'claimed' as const : 'duplicate' as const;
    });
    if (outcome === 'missing') return NextResponse.json({ error: 'job_not_found' }, { status: 404 });
    if (outcome === 'saturated') return NextResponse.json({ error: 'global_heavy_job_limit' }, { status: 429 });
    if (outcome === 'duplicate') return NextResponse.json({ duplicate: true }, { status: 200 });
    const job = await db.canonicalJob.findUniqueOrThrow({ where: { id: canonicalJobId } });
    try {
      const operation = await startCloudRunJob(job.kind, job.id);
      await db.auditEvent.create({ data: {
        workspaceId: job.workspaceId,
        action: 'job.dispatched',
        targetType: 'canonical_job',
        targetId: job.id,
        requestId: `dispatch:${job.id}:${job.attempt}`,
        evidence: { operation, kind: job.kind },
      } });
      return NextResponse.json({ accepted: true, operation }, { status: 202 });
    } catch (error) {
      await db.canonicalJob.update({ where: { id: job.id }, data: {
        state: 'INTERRUPTED', errorCode: 'cloud_run_dispatch_failed', errorDetail: String(error).slice(0, 2000),
      } });
      throw error;
    }
  } catch (error) { return apiError(error); }
}
