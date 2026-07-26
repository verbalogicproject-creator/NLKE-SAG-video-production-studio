import { Storage } from '@google-cloud/storage';
import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { apiError } from '@/lib/http';

type FailedArtifact = {
  id: string;
  storage_namespace: string;
  storage_key: string;
  storage_version: string;
};

export async function POST(request: Request) {
  try {
    if (process.env.NODE_ENV === 'production' && !request.headers.get('x-cloudscheduler')) {
      return NextResponse.json({ error: 'forbidden' }, { status: 403 });
    }
    const bucket = process.env.GCS_MEDIA_BUCKET;
    if (!bucket) return NextResponse.json({ error: 'storage_not_configured' }, { status: 503 });
    const rows = await db.$queryRaw<FailedArtifact[]>`
      SELECT artifact.id,artifact.storage_namespace,artifact.storage_key,artifact.storage_version
      FROM sag.artifacts artifact
      JOIN sag.jobs job ON job.id=artifact.job_id
      WHERE artifact.storage_backend='gcs'
        AND artifact.storage_namespace=${bucket}
        AND artifact.storage_key IS NOT NULL
        AND artifact.storage_version IS NOT NULL
        AND job.state IN ('observed_failure','execution_failed','cancelled','timeout','interrupted')
        AND artifact.created_at::timestamptz < now() - interval '7 days'
      ORDER BY artifact.created_at
      LIMIT 100
    `;
    const storage = new Storage();
    let deleted = 0;
    for (const row of rows) {
      if (!row.storage_key.startsWith('workspaces/')) continue;
      try {
        await storage.bucket(bucket).file(row.storage_key, { generation: row.storage_version }).delete({
          ifGenerationMatch: Number(row.storage_version),
        });
      } catch (error) {
        if (Number((error as { code?: number }).code) !== 404) throw error;
      }
      await db.$executeRaw`
        UPDATE sag.artifacts SET storage_key=NULL,storage_version=NULL
        WHERE id=${row.id} AND storage_key=${row.storage_key} AND storage_version=${row.storage_version}
      `;
      deleted += 1;
    }
    return NextResponse.json({ inspected: rows.length, deleted });
  } catch (error) {
    return apiError(error);
  }
}
