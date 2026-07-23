import { PrismaClient } from '@prisma/client';
import type PgBoss from 'pg-boss';
import type { VerticalVariant } from '@verbalogix/media-contracts';
import { engineJob, engineSuggestions } from '../engine.js';

const db = new PrismaClient();
const TERMINAL_FAILURE = new Set(['observed_failure', 'execution_failed', 'cancelled', 'timeout', 'interrupted']);
const ACTIVE = new Set(['queued', 'running', 'accepted', 'dispatched', 'rendering', 'artifact_written', 'awaiting_observation']);

export async function syncChamber(runId: string, boss: PgBoss): Promise<void> {
  const run = await db.chamberRun.findUnique({
    where: { id: runId },
    include: { project: { include: { workspace: true } }, variants: true },
  });
  if (!run || ['READY_TO_PUBLISH', 'FAILED', 'CANCELLED', 'HALTED_BRAND_VIOLATION'].includes(run.status)) return;
  const workspaceId = run.project.workspaceId;
  let reschedule = false;

  if (run.analysisJobId && ['INGESTING', 'ANALYZING'].includes(run.status)) {
    const job = await engineJob(workspaceId, run.analysisJobId);
    if (job.state === 'observed_success') {
      const { suggestions } = await engineSuggestions(workspaceId, run.engineProjectId, job.id);
      for (const suggestion of suggestions) {
        const variant = suggestion.evidence.target_variant as VerticalVariant | undefined;
        if (!variant) continue;
        await db.chamberVariant.update({
          where: { chamberRunId_variant: { chamberRunId: run.id, variant } },
          data: {
            suggestionId: suggestion.id,
            status: suggestion.state === 'halted_brand_violation' ? 'HALTED_BRAND_VIOLATION' : 'DRAFT_READY',
            warningDetails: {
              reason: suggestion.reason,
              confidence: suggestion.confidence,
              warnings: suggestion.evidence.draft_plan?.warnings ?? [],
              brandViolations: suggestion.evidence.brand_violations ?? [],
            },
          },
        });
      }
      const refreshed = await db.chamberVariant.findMany({ where: { chamberRunId: run.id } });
      const allHalted = refreshed.every((variant) => variant.status === 'HALTED_BRAND_VIOLATION');
      await db.chamberRun.update({ where: { id: run.id }, data: { status: allHalted ? 'HALTED_BRAND_VIOLATION' : 'DRAFTS_READY' } });
    } else if (TERMINAL_FAILURE.has(job.state)) {
      await db.chamberRun.update({
        where: { id: run.id },
        data: { status: job.state === 'cancelled' ? 'CANCELLED' : 'FAILED', errorCode: job.error_code, errorDetail: job.error_detail },
      });
      return;
    } else {
      reschedule = true;
    }
  }

  const rendering = run.variants.filter((variant) => variant.renderJobId && ['RENDERING', 'VERIFYING'].includes(variant.status));
  for (const variant of rendering) {
    const job = await engineJob(workspaceId, variant.renderJobId!);
    if (job.state === 'observed_success') {
      await db.chamberVariant.update({
        where: { id: variant.id },
        data: { status: 'READY_TO_PUBLISH', deliverableAssetId: job.result_artifact_id },
      });
    } else if (job.state === 'awaiting_observation') {
      await db.chamberVariant.update({ where: { id: variant.id }, data: { status: 'VERIFYING' } });
      reschedule = true;
    } else if (TERMINAL_FAILURE.has(job.state)) {
      await db.chamberVariant.update({
        where: { id: variant.id },
        data: { status: job.state === 'cancelled' ? 'CANCELLED' : 'FAILED', warningDetails: { code: job.error_code, detail: job.error_detail } },
      });
    } else if (ACTIVE.has(job.state)) {
      reschedule = true;
    }
  }

  const variants = await db.chamberVariant.findMany({ where: { chamberRunId: run.id } });
  const selected = variants.filter((variant) => variant.engineProjectId);
  if (selected.length > 0 && selected.every((variant) => variant.status === 'READY_TO_PUBLISH')) {
    await db.chamberRun.update({ where: { id: run.id }, data: { status: 'READY_TO_PUBLISH' } });
    return;
  }
  if (selected.some((variant) => ['RENDERING', 'VERIFYING'].includes(variant.status))) {
    await db.chamberRun.update({ where: { id: run.id }, data: { status: 'RENDERING' } });
  }
  if (reschedule) {
    await boss.send('chamber.sync', { runId }, { startAfter: new Date(Date.now() + 2_000), singletonKey: `chamber-${runId}` });
  }
}
