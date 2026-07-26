import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { flushOutbox } from '@/lib/cloud-dispatch';
import { apiError } from '@/lib/http';

export async function POST(request: Request) {
  try {
    if (process.env.NODE_ENV === 'production' && !request.headers.get('x-cloudscheduler')) {
      return NextResponse.json({ error: 'forbidden' }, { status: 403 });
    }
    const expired = await db.canonicalJob.findMany({
      where: { state: { in: ['CLAIMED', 'RUNNING'] }, leaseExpiresAt: { lt: new Date() } },
      select: { id: true, attempt: true, maxAttempts: true }, take: 100,
    });
    let interrupted = 0;
    for (const job of expired) {
      await db.$transaction(async (tx) => {
        const changed = await tx.canonicalJob.updateMany({
          where: { id: job.id, state: { in: ['CLAIMED', 'RUNNING'] }, leaseExpiresAt: { lt: new Date() } },
          data: job.attempt < job.maxAttempts
            ? { state: 'INTERRUPTED', errorCode: 'lease_expired', leaseExpiresAt: null }
            : { state: 'FAILED', errorCode: 'attempt_limit_exhausted', leaseExpiresAt: null },
        });
        if (!changed.count) return;
        interrupted += 1;
        if (job.attempt < job.maxAttempts) await tx.outboxEvent.create({ data: { jobId: job.id } });
      });
    }
    const dispatched = await flushOutbox();
    return NextResponse.json({ interrupted, dispatched });
  } catch (error) { return apiError(error); }
}
