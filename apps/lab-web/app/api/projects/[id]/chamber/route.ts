import { NextResponse } from 'next/server';
import { randomUUID } from 'node:crypto';
import { VerticalVariantSchema, type VerticalVariant } from '@verbalogix/media-contracts';
import { db } from '@/lib/db';
import { resolveBrandContract } from '@/lib/brand-contract';
import { sagEngine } from '@/lib/engine';
import { apiError, jsonSafe } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

const DEFAULT_VARIANTS = ['YT_SHORTS_9_16', 'TIKTOK_9_16', 'IG_REELS_9_16'] as const;

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const body = await request.json();
    const requestId = body.requestId ? String(body.requestId).trim() : `analysis:${randomUUID()}`;
    if (!requestId || requestId.length > 180) {
      return NextResponse.json({ error: 'invalid_request_id' }, { status: 422 });
    }
    const project = await db.project.findFirst({ where: { id, workspaceId } });
    if (!project?.engineProjectId) return NextResponse.json({ error: 'project_not_found' }, { status: 404 });
    const engineProjectId = project.engineProjectId;
    const workspace = await db.workspace.findUniqueOrThrow({ where: { id: workspaceId } });
    const activeAnalysis = await db.chamberRun.count({
      where: { project: { workspaceId }, status: { in: ['INGESTING', 'ANALYZING'] } },
    });
    if (process.env.CLOUD_EXECUTION_ENABLED !== 'true' && activeAnalysis >= workspace.analysisConcurrencyLimit) {
      return NextResponse.json({ error: 'analysis_concurrency_quota_exceeded' }, { status: 409 });
    }
    const asset = await db.asset.findFirst({ where: { id: String(body.sourceAssetId), projectId: id, kind: 'RAW' } });
    if (!asset?.engineAssetId || !asset.sha256) return NextResponse.json({ error: 'source_asset_not_ready' }, { status: 422 });
    const sourceEngineAssetId = asset.engineAssetId;
    const sourceSha256 = asset.sha256;
    const variants: VerticalVariant[] = (body.variants ?? DEFAULT_VARIANTS).map((value: unknown) => VerticalVariantSchema.parse(value));
    if (process.env.CLOUD_EXECUTION_ENABLED === 'true') {
      const duplicate = await db.canonicalJob.findUnique({ where: { workspaceId_requestId: { workspaceId, requestId } } });
      if (duplicate) {
        if (duplicate.kind !== 'ANALYSIS') return NextResponse.json({ error: 'request_id_conflict' }, { status: 409 });
        const existingRun = await db.chamberRun.findFirst({
          where: { id: duplicate.canonicalEntityId, project: { workspaceId } }, include: { variants: true },
        });
        if (!existingRun) return NextResponse.json({ error: 'request_id_conflict' }, { status: 409 });
        return NextResponse.json(jsonSafe({ run: existingRun, job: { id: duplicate.id, state: duplicate.state.toLowerCase() } }), { status: 202 });
      }
    }
    const engineProject = await sagEngine.project(workspaceId, engineProjectId);
    const brand = await resolveBrandContract(workspaceId);
    const analysisRequest = {
      sourceAssetId: sourceEngineAssetId,
      engineProjectId,
      sourceRevision: engineProject.project.revision,
      sourceSha256,
      variants,
      language: body.language ?? 'auto',
      prompt: body.prompt ? String(body.prompt).slice(0, 2000) : undefined,
    };
    if (process.env.CLOUD_EXECUTION_ENABLED !== 'true') {
      const job = await sagEngine.startAnalysis(workspaceId, analysisRequest, brand);
      const run = await db.chamberRun.create({ data: {
        projectId: id,
        engineProjectId,
        sourceEngineAssetId,
        sourceRevision: engineProject.project.revision,
        sourceSha256,
        requestedVariants: variants,
        language: body.language ?? 'auto',
        prompt: body.prompt ? String(body.prompt).slice(0, 2000) : null,
        brandSkillVersion: brand.version,
        brandContractHash: brand.contract_hash,
        brandContractSnapshot: brand,
        analysisJobId: job.id,
        status: 'ANALYZING',
        variants: { create: variants.map((variant) => ({ variant })) },
      }, include: { variants: true } });
      return NextResponse.json(jsonSafe({ run, job }), { status: 202 });
    }
    const runId = randomUUID();
    const jobId = randomUUID();
    const outcome = await db.$transaction(async (tx) => {
      await tx.$executeRaw`SELECT pg_advisory_xact_lock(hashtext(${`sag-analysis:${workspaceId}`}))`;
      const duplicate = await tx.canonicalJob.findUnique({ where: { workspaceId_requestId: { workspaceId, requestId } } });
      if (duplicate) {
        if (duplicate.kind !== 'ANALYSIS') throw Object.assign(new Error('request ID was already used for another mutation'), { status: 409 });
        const existingRun = await tx.chamberRun.findUniqueOrThrow({ where: { id: duplicate.canonicalEntityId }, include: { variants: true } });
        return { run: existingRun, jobId: duplicate.id };
      }
      const lockedActive = await tx.chamberRun.count({
        where: { project: { workspaceId }, status: { in: ['INGESTING', 'ANALYZING'] } },
      });
      if (lockedActive >= workspace.analysisConcurrencyLimit) {
        throw Object.assign(new Error('analysis concurrency quota exceeded'), { status: 409 });
      }
      const created = await tx.chamberRun.create({ data: {
        id: runId, projectId: id, engineProjectId,
        sourceEngineAssetId, sourceRevision: engineProject.project.revision,
        sourceSha256, requestedVariants: variants,
        language: analysisRequest.language, prompt: analysisRequest.prompt ?? null,
        brandSkillVersion: brand.version, brandContractHash: brand.contract_hash,
        brandContractSnapshot: brand, analysisJobId: jobId, status: 'ANALYZING',
        variants: { create: variants.map((variant) => ({ variant })) },
      }, include: { variants: true } });
      await tx.canonicalJob.create({ data: {
        id: jobId, workspaceId, projectId: id, kind: 'ANALYSIS', state: 'DISPATCH_PENDING',
        requestId, canonicalEntityId: runId,
        inputVersion: 'sag-analysis-1', inputSnapshot: {
          ...analysisRequest, brandContract: brand, candidateCount: Math.max(3, variants.length),
        }, outbox: { create: {} },
      } });
      return { run: created, jobId };
    });
    return NextResponse.json(jsonSafe({ run: outcome.run, job: { id: outcome.jobId, state: 'queued' } }), { status: 202 });
  } catch (error) {
    return apiError(error);
  }
}
