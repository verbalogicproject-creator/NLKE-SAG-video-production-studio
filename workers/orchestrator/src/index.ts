import PgBoss from 'pg-boss';
import { syncChamber } from './jobs/chamber-sync.js';

async function main() {
  if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL is required');
  const boss = new PgBoss({ connectionString: process.env.DATABASE_URL, schema: 'pgboss', retryLimit: 5, retryBackoff: true });
  boss.on('error', (error) => console.error('[pg-boss]', error));
  await boss.start();
  await boss.work('chamber.sync', { batchSize: 2 }, async (jobs) => {
    await Promise.all(jobs.map((job) => syncChamber(String((job.data as { runId: string }).runId), boss)));
  });
  console.log('[orchestrator] ready · chamber.sync');
  process.on('SIGTERM', async () => {
    await boss.stop({ graceful: true, timeout: 30_000 });
    process.exit(0);
  });
}

main().catch((error) => {
  console.error('[orchestrator] fatal', error);
  process.exit(1);
});
