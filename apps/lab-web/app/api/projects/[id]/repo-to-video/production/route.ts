import { NextResponse } from 'next/server';
import { sagEngine } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { repoVideoEngineProject } from '@/lib/repo-to-video-route';
import { requireWorkspace } from '@/lib/workspace';

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const sequenceId = new URL(request.url).searchParams.get('sequence_id') ?? '';
    const engineProjectId = await repoVideoEngineProject(id, sequenceId, workspaceId);
    return NextResponse.json(await sagEngine.productionSession(workspaceId, engineProjectId));
  } catch (error) { return apiError(error); }
}

export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const body = await request.json() as Record<string, unknown>;
    const engineProjectId = await repoVideoEngineProject(id, String(body.sequence_id ?? ''), workspaceId);
    const { sequence_id: _sequenceId, ...update } = body;
    return NextResponse.json(await sagEngine.updateProductionSession(workspaceId, engineProjectId, update));
  } catch (error) { return apiError(error); }
}
