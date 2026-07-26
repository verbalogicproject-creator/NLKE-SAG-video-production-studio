import { NextResponse } from 'next/server';
import { sagEngine, type CreativeBrief, type Storyboard } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { repoVideoEngineProject } from '@/lib/repo-to-video-route';
import { requireWorkspace } from '@/lib/workspace';

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const body = await request.json() as Record<string, unknown>;
    const engineProjectId = await repoVideoEngineProject(id, String(body.sequence_id ?? ''), workspaceId);
    return NextResponse.json(await sagEngine.previewRepoToVideoPrompts(workspaceId, engineProjectId, {
      creative_instruction: String(body.creative_instruction ?? ''),
      creative_brief: body.creative_brief as CreativeBrief | undefined,
      storyboard: body.storyboard as Storyboard | undefined,
      aspect_ratio: body.aspect_ratio === '16:9' ? '16:9' : '9:16',
      active_scene_id: body.active_scene_id ? String(body.active_scene_id) : undefined,
    }));
  } catch (error) { return apiError(error); }
}
