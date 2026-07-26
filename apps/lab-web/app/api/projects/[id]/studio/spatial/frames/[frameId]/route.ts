import { NextResponse } from 'next/server';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';
import { sagEngine } from '@/lib/engine';
import { studioEngineProject } from '@/lib/studio-target';

export async function GET(_request: Request, { params }: { params: Promise<{ id: string; frameId: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id, frameId } = await params;
    return NextResponse.json(await sagEngine.spatialFrame(
      workspaceId, await studioEngineProject(id, workspaceId), frameId,
    ));
  } catch (error) { return apiError(error); }
}
