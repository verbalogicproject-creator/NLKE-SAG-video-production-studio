import { NextResponse } from 'next/server';
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
    const project = await db.project.findFirst({ where: { id, workspaceId } });
    if (!project?.engineProjectId) return NextResponse.json({ error: 'project_not_found' }, { status: 404 });
    const workspace = await db.workspace.findUniqueOrThrow({ where: { id: workspaceId } });
    const activeAnalysis = await db.chamberRun.count({
      where: { project: { workspaceId }, status: { in: ['INGESTING', 'ANALYZING'] } },
    });
    if (activeAnalysis >= workspace.analysisConcurrencyLimit) {
      return NextResponse.json({ error: 'analysis_concurrency_quota_exceeded' }, { status: 409 });
    }
    const asset = await db.asset.findFirst({ where: { id: String(body.sourceAssetId), projectId: id, kind: 'RAW' } });
    if (!asset?.engineAssetId || !asset.sha256) return NextResponse.json({ error: 'source_asset_not_ready' }, { status: 422 });
    const variants: VerticalVariant[] = (body.variants ?? DEFAULT_VARIANTS).map((value: unknown) => VerticalVariantSchema.parse(value));
    const engineProject = await sagEngine.project(workspaceId, project.engineProjectId);
    const brand = await resolveBrandContract(workspaceId);
    const job = await sagEngine.startAnalysis(workspaceId, {
      sourceAssetId: asset.engineAssetId,
      engineProjectId: project.engineProjectId,
      sourceRevision: engineProject.project.revision,
      sourceSha256: asset.sha256,
      variants,
      language: body.language ?? 'auto',
      prompt: body.prompt ? String(body.prompt).slice(0, 2000) : undefined,
    }, brand);
    const run = await db.chamberRun.create({
      data: {
        projectId: id,
        engineProjectId: project.engineProjectId,
        sourceEngineAssetId: asset.engineAssetId,
        sourceRevision: engineProject.project.revision,
        sourceSha256: asset.sha256,
        requestedVariants: variants,
        language: body.language ?? 'auto',
        prompt: body.prompt ? String(body.prompt).slice(0, 2000) : null,
        brandSkillVersion: brand.version,
        brandContractHash: brand.contract_hash,
        brandContractSnapshot: brand,
        analysisJobId: job.id,
        status: 'ANALYZING',
        variants: { create: variants.map((variant) => ({ variant })) },
      },
      include: { variants: true },
    });
    return NextResponse.json(jsonSafe({ run, job }), { status: 202 });
  } catch (error) {
    return apiError(error);
  }
}
