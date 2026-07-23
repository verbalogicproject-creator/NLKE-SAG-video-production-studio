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
    const claimed = await db.canonicalJob.updateMany({
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
    if (!claimed.count) return NextResponse.json({ duplicate: true }, { status: 200 });
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
