import { NextResponse } from 'next/server';
import { sagEngine } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { repoVideoEngineProject } from '@/lib/repo-to-video-route';
import { requireWorkspace } from '@/lib/workspace';

export async function GET(request: Request, { params }: { params: Promise<{ id: string; receiptId: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id, receiptId } = await params;
    const sequenceId = new URL(request.url).searchParams.get('sequence_id') ?? '';
    const engineProjectId = await repoVideoEngineProject(id, sequenceId, workspaceId);
    return NextResponse.json(await sagEngine.pollRepoToVideoGeneration(workspaceId, engineProjectId, receiptId));
  } catch (error) { return apiError(error); }
}
