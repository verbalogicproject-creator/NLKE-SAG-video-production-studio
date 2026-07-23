import { db } from '@/lib/db';
import { sagEngine } from '@/lib/engine';
import { prismaJson } from '@/lib/http';

const TERMINAL_FAILURE = new Set(['observed_failure', 'execution_failed', 'cancelled', 'timeout', 'interrupted']);

export async function reconcileChamberRun(runId: string, workspaceId: string): Promise<void> {
  const run = await db.chamberRun.findFirst({
    where: { id: runId, project: { workspaceId } },
    include: { variants: true },
  });
  if (!run || ['READY_TO_PUBLISH', 'FAILED', 'CANCELLED', 'HALTED_BRAND_VIOLATION'].includes(run.status)) return;

  if (run.analysisJobId && ['INGESTING', 'ANALYZING'].includes(run.status)) {
    const job = await sagEngine.job(workspaceId, run.analysisJobId);
    if (job.state === 'observed_success') {
      const { suggestions } = await sagEngine.suggestions(workspaceId, run.engineProjectId, job.id);
      for (const suggestion of suggestions) {
        const variant = suggestion.evidence.target_variant;
        if (!variant || !run.requestedVariants.includes(variant)) continue;
        await db.chamberVariant.update({
          where: { chamberRunId_variant: { chamberRunId: run.id, variant } },
          data: {
            suggestionId: suggestion.id,
            status: suggestion.state === 'halted_brand_violation' ? 'HALTED_BRAND_VIOLATION' : 'DRAFT_READY',
            warningDetails: prismaJson({
              reason: suggestion.reason,
              confidence: suggestion.confidence,
              warnings: suggestion.evidence.draft_plan?.warnings ?? [],
              brandViolations: suggestion.evidence.brand_violations ?? [],
            }),
          },
        });
      }
      const drafts = await db.chamberVariant.findMany({ where: { chamberRunId: run.id } });
      const allHalted = drafts.length > 0 && drafts.every((entry) => entry.status === 'HALTED_BRAND_VIOLATION');
      await db.chamberRun.update({ where: { id: run.id }, data: { status: allHalted ? 'HALTED_BRAND_VIOLATION' : 'DRAFTS_READY' } });
    } else if (TERMINAL_FAILURE.has(job.state)) {
      await db.chamberRun.update({
        where: { id: run.id },
        data: {
          status: job.state === 'cancelled' ? 'CANCELLED' : 'FAILED',
          errorCode: job.error_code,
          errorDetail: job.error_detail,
        },
      });
      return;
    }
  }

  const rendering = run.variants.filter((entry) => entry.renderJobId && ['RENDERING', 'VERIFYING'].includes(entry.status));
  for (const variant of rendering) {
    const job = await sagEngine.job(workspaceId, variant.renderJobId!);
    if (job.state === 'observed_success') {
      const artifact = await sagEngine.artifact(workspaceId, job.result_artifact_id!);
      const controlAsset = await db.asset.upsert({
        where: { engineAssetId: artifact.id },
        update: { sha256: artifact.sha256, verifiedAt: new Date(), metadata: prismaJson(artifact.provenance) },
        create: {
          projectId: run.projectId,
          kind: 'DELIVERABLE',
          managedUri: artifact.managed_uri,
          mimeType: artifact.mime_type,
          sizeBytes: BigInt(artifact.byte_size),
          engineAssetId: artifact.id,
          sha256: artifact.sha256,
          verifiedAt: new Date(),
          metadata: prismaJson(artifact.provenance),
        },
      });
      await db.chamberVariant.update({
        where: { id: variant.id },
        data: { status: 'READY_TO_PUBLISH', deliverableAssetId: controlAsset.id },
      });
    } else if (job.state === 'awaiting_observation') {
      await db.chamberVariant.update({ where: { id: variant.id }, data: { status: 'VERIFYING' } });
    } else if (TERMINAL_FAILURE.has(job.state)) {
      await db.chamberVariant.update({
        where: { id: variant.id },
        data: {
          status: job.state === 'cancelled' ? 'CANCELLED' : 'FAILED',
          warningDetails: { code: job.error_code, detail: job.error_detail },
        },
      });
    }
  }

  const variants = await db.chamberVariant.findMany({ where: { chamberRunId: run.id } });
  const accepted = variants.filter((entry) => entry.engineProjectId);
  if (accepted.length > 0 && accepted.every((entry) => entry.status === 'READY_TO_PUBLISH')) {
    await db.chamberRun.update({ where: { id: run.id }, data: { status: 'READY_TO_PUBLISH' } });
  } else if (accepted.some((entry) => ['RENDERING', 'VERIFYING'].includes(entry.status))) {
    await db.chamberRun.update({ where: { id: run.id }, data: { status: 'RENDERING' } });
  }
}
