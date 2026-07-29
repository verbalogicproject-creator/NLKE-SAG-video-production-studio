import { NextResponse } from 'next/server';
import { sagEngine } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';
import { studioTarget } from '@/lib/studio-target';

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const { sequence } = await studioTarget(id, workspaceId, new URL(request.url).searchParams.get('sequence_id'));
    return NextResponse.json(await sagEngine.protectedScreenComposites(workspaceId, sequence.engineProjectId));
  } catch (error) {
    return apiError(error);
  }
}
