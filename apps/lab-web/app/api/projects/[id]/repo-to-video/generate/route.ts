import { NextResponse } from 'next/server';
import { sagEngine, type CreativeBrief, type Storyboard } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { repoVideoEngineProject, requireHumanConfirmation } from '@/lib/repo-to-video-route';
import { requireWorkspace } from '@/lib/workspace';

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const body = await request.json() as Record<string, unknown>;
    requireHumanConfirmation(request, body);
    const engineProjectId = await repoVideoEngineProject(id, String(body.sequence_id ?? ''), workspaceId);
    const aspectRatio = body.aspect_ratio === '16:9' ? '16:9' : '9:16';
    return NextResponse.json(await sagEngine.generateRepoToVideo(workspaceId, engineProjectId, {
      storyboard: body.storyboard as Storyboard, creative_brief: body.creative_brief as CreativeBrief,
      storyboard_receipt_id: String(body.storyboard_receipt_id),
      expected_revision: Number(body.expected_revision), confirmation_id: String(body.confirmation_id), aspect_ratio: aspectRatio,
    }));
  } catch (error) { return apiError(error); }
}
