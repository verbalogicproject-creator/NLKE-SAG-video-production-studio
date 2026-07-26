import { NextResponse } from 'next/server';
import { sagEngine } from '@/lib/engine';
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
    return NextResponse.json(await sagEngine.commitRepoToVideoStoryboard(workspaceId, engineProjectId, {
      receipt_id: String(body.receipt_id ?? ''), expected_revision: Number(body.expected_revision),
      confirmation_id: String(body.confirmation_id),
    }));
  } catch (error) { return apiError(error); }
}
