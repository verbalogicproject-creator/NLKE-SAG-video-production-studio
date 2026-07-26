import { CloudTasksClient } from '@google-cloud/tasks';
import { GoogleAuth } from 'google-auth-library';
import type { CanonicalJobKind } from '@prisma/client';
import { db } from '@/lib/db';

const tasks = new CloudTasksClient();

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

export async function flushOutbox(limit = 50): Promise<number> {
  if (process.env.QUEUE_BACKEND !== 'cloud-tasks' || process.env.CLOUD_EXECUTION_ENABLED !== 'true') return 0;
  const entries = await db.outboxEvent.findMany({
    where: { state: 'PENDING', availableAt: { lte: new Date() } },
    include: { job: true },
    orderBy: { createdAt: 'asc' },
    take: Math.min(limit, 100),
  });
  const project = required('GOOGLE_CLOUD_PROJECT');
  const location = required('GCP_REGION');
  const queue = required('CLOUD_TASKS_QUEUE');
  const dispatchUrl = required('DISPATCH_URL');
  const serviceAccountEmail = required('TASK_INVOKER_SERVICE_ACCOUNT');
  const parent = tasks.queuePath(project, location, queue);
  let count = 0;
  for (const entry of entries) {
    try {
      await tasks.createTask({ parent, task: { httpRequest: {
        httpMethod: 'POST',
        url: `${dispatchUrl.replace(/\/$/, '')}/api/internal/dispatch`,
        headers: { 'content-type': 'application/json' },
        body: Buffer.from(JSON.stringify({ canonicalJobId: entry.jobId })).toString('base64'),
        oidcToken: { serviceAccountEmail, audience: dispatchUrl },
      } } });
      await db.$transaction([
        db.outboxEvent.update({ where: { id: entry.id }, data: { state: 'DISPATCHED', dispatchedAt: new Date(), attempt: { increment: 1 } } }),
        db.canonicalJob.updateMany({ where: { id: entry.jobId, state: 'DISPATCH_PENDING' }, data: { state: 'QUEUED' } }),
      ]);
      count += 1;
    } catch (error) {
      await db.outboxEvent.update({ where: { id: entry.id }, data: {
        attempt: { increment: 1 },
        lastError: String(error).slice(0, 2000),
        availableAt: new Date(Date.now() + Math.min(300, 2 ** Math.min(entry.attempt, 8)) * 1000),
      } });
    }
  }
  return count;
}

function cloudRunJobName(kind: CanonicalJobKind): string {
  const names: Record<CanonicalJobKind, string | undefined> = {
    INTAKE: process.env.CLOUD_RUN_INTAKE_JOB,
    ANALYSIS: process.env.CLOUD_RUN_ANALYSIS_JOB,
    RENDER: process.env.CLOUD_RUN_RENDER_JOB,
    OBSERVE: process.env.CLOUD_RUN_OBSERVER_JOB,
    PUBLISH_YOUTUBE: process.env.CLOUD_RUN_PUBLISH_JOB,
  };
  const name = names[kind];
  if (!name) throw new Error(`Cloud Run Job is not configured for ${kind}`);
  return name;
}

export async function startCloudRunJob(kind: CanonicalJobKind, canonicalJobId: string): Promise<string> {
  const project = required('GOOGLE_CLOUD_PROJECT');
  const region = required('GCP_REGION');
  const jobName = cloudRunJobName(kind);
  const resource = `projects/${project}/locations/${region}/jobs/${jobName}`;
  const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
  const client = await auth.getClient();
  const response = await client.request<{ name?: string }>({
    url: `https://run.googleapis.com/v2/${resource}:run`,
    method: 'POST',
    data: { overrides: { containerOverrides: [{ env: [{ name: 'SAG_CANONICAL_JOB_ID', value: canonicalJobId }] }] } },
  });
  return response.data.name ?? resource;
}
