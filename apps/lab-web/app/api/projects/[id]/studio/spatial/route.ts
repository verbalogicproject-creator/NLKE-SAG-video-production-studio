import { NextResponse } from 'next/server';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';
import { sagEngine } from '@/lib/engine';
import { studioEngineProject } from '@/lib/studio-target';

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const query = new URL(request.url).searchParams;
    return NextResponse.json(await sagEngine.spatialSnapshot(workspaceId, await studioEngineProject(id, workspaceId, query.get('sequence_id')), {
      focusId: query.get('focus_id'), depth: query.get('depth') ?? 'context',
      hopCount: Number(query.get('hop_count') ?? 2),
    }));
  } catch (error) {
    return apiError(error);
  }
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const body = await request.json();
    if (body.operation !== 'ack') return NextResponse.json({ error: 'unsupported_spatial_operation' }, { status: 422 });
    return NextResponse.json(await sagEngine.acknowledgeSpatialDirective(
      workspaceId, String(body.receiptId), body.acknowledgement ?? {},
    ));
  } catch (error) {
    return apiError(error);
  }
}
