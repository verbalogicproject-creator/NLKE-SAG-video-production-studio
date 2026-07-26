import { NextResponse } from 'next/server';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';
import { sagEngine } from '@/lib/engine';
import { studioEngineProject } from '@/lib/studio-target';

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    return NextResponse.json(await sagEngine.currentSpatialFrame(
      workspaceId, await studioEngineProject(id, workspaceId),
    ));
  } catch (error) { return apiError(error); }
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    return NextResponse.json(await sagEngine.declareSpatialFrame(
      workspaceId, await studioEngineProject(id, workspaceId), await request.json(),
    ), { status: 201 });
  } catch (error) { return apiError(error); }
}
