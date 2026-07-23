import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { flushOutbox } from '@/lib/cloud-dispatch';
import { apiError } from '@/lib/http';

export async function POST(request: Request) {
  try {
    if (process.env.NODE_ENV === 'production' && !request.headers.get('x-cloudscheduler')) {
      return NextResponse.json({ error: 'forbidden' }, { status: 403 });
    }
    const interrupted = await db.canonicalJob.updateMany({
      where: { state: { in: ['CLAIMED', 'RUNNING'] }, leaseExpiresAt: { lt: new Date() } },
      data: { state: 'INTERRUPTED', errorCode: 'lease_expired' },
    });
    const dispatched = await flushOutbox();
    return NextResponse.json({ interrupted: interrupted.count, dispatched });
  } catch (error) { return apiError(error); }
}
