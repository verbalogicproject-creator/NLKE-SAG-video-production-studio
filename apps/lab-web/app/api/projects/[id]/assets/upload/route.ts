import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { sagEngine } from '@/lib/engine';
import { apiError, jsonSafe } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const project = await db.project.findFirst({ where: { id, workspaceId } });
    if (!project?.engineProjectId) return NextResponse.json({ error: 'project_not_found' }, { status: 404 });
    const incoming = await request.formData();
    const file = incoming.get('file');
    if (!(file instanceof File)) return NextResponse.json({ error: 'file_required' }, { status: 422 });
    const forwarded = new FormData();
    forwarded.set('file', file, file.name);
    forwarded.set('request_id', `lab-upload-${randomUUID()}`);
    forwarded.set('actor', 'verbalogix-web');
    const result = await sagEngine.upload(workspaceId, project.engineProjectId, forwarded) as {
      asset?: Record<string, unknown>;
      receipt?: { project_revision?: number };
    };
    if (!result.asset) throw new Error('Engine did not return an imported asset');
    const engineAsset = result.asset;
    const asset = await db.asset.create({ data: {
      projectId: project.id,
      kind: 'RAW',
      r2Bucket: 'local-engine',
      r2Key: String(engineAsset.managed_uri ?? engineAsset.id),
      mimeType: typeof engineAsset.mime_type === 'string' ? engineAsset.mime_type : file.type,
      sizeBytes: BigInt(Number(engineAsset.byte_size ?? file.size)),
      durationMs: engineAsset.duration_ticks ? Math.round(Number(engineAsset.duration_ticks) / 120) : null,
      engineAssetId: String(engineAsset.id),
      sha256: String(engineAsset.sha256 ?? ''),
      metadata: engineAsset,
    } });
    const engineState = await sagEngine.project(workspaceId, project.engineProjectId);
    await db.project.update({ where: { id: project.id }, data: { status: 'READY', engineRevision: engineState.project.revision } });
    return NextResponse.json(jsonSafe({ asset, engine: result }), { status: 201 });
  } catch (error) {
    return apiError(error);
  }
}
