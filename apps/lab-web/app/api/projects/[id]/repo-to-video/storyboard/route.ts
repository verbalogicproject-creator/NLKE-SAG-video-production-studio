import { NextResponse } from 'next/server';
import { sagEngine } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { directorInput, repoVideoEngineProject } from '@/lib/repo-to-video-route';
import { requireWorkspace } from '@/lib/workspace';

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const body = await request.json() as Record<string, unknown>;
    const engineProjectId = await repoVideoEngineProject(id, String(body.sequence_id ?? ''), workspaceId);
    return NextResponse.json(await sagEngine.repoToVideoStoryboard(workspaceId, engineProjectId, directorInput(body)));
  } catch (error) { return apiError(error); }
}
