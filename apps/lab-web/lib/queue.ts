import PgBoss from 'pg-boss';

/**
 * pg-boss runs the job queue on the same Neon Postgres that holds the
 * domain tables. Names are kept in an enum so workers and web agree.
 */

export const Queues = {
  TRANSCRIBE: 'job.transcribe',
  ATOMIZE:    'job.atomize',
  RENDER:     'job.render',
  PUBLISH:    'job.publish',
  CHAMBER_SYNC: 'chamber.sync',
} as const;

export type QueueName = (typeof Queues)[keyof typeof Queues];

// ── Typed payloads ────────────────────────────────────────────────

export type TranscribeJob = {
  projectId: string;
  assetId: string;          // the RAW asset to transcribe
};

export type AtomizeJob = {
  projectId: string;
  transcriptAssetId: string;
};

export type RenderJob = {
  renderJobId: string;       // RenderJob row id; worker reads EDL from the row
};

export type PublishJob = {
  renderJobId: string;
  platforms: Array<'YOUTUBE' | 'LINKEDIN' | 'TIKTOK' | 'INSTAGRAM' | 'FACEBOOK'>;
};

export type ChamberSyncJob = { runId: string };

// ── Singleton ─────────────────────────────────────────────────────

let bossPromise: Promise<PgBoss> | null = null;

export function getQueue(): Promise<PgBoss> {
  if (!bossPromise) {
    const boss = new PgBoss({
      connectionString: process.env.DATABASE_URL,
      schema: 'pgboss',
      retryLimit: 3,
      retryBackoff: true,
      expireInHours: 4,
    });
    bossPromise = boss.start().then(() => boss);
  }
  return bossPromise;
}

export async function enqueue<T>(name: QueueName, data: T): Promise<string> {
  const boss = await getQueue();
  const id = await boss.send(name, data as object);
  if (!id) throw new Error(`enqueue failed for ${name}`);
  return id;
}
