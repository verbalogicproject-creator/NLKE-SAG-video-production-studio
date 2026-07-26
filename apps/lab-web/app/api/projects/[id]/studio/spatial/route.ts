import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';
import { sagEngine } from '@/lib/engine';

async function target(id: string, workspaceId: string) {
  const row = await db.project.findFirst({ where: { id, workspaceId } });
  if (!row?.engineProjectId) throw Object.assign(new Error('Studio project is not initialized'), { status: 409 });
  return row.engineProjectId;
}

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const engineProjectId = await target(id, workspaceId);
    const query = new URL(request.url).searchParams;
    return NextResponse.json(await sagEngine.spatialSnapshot(workspaceId, engineProjectId, {
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
    await target(id, workspaceId);
    const body = await request.json();
    if (body.operation !== 'ack') return NextResponse.json({ error: 'unsupported_spatial_operation' }, { status: 422 });
    return NextResponse.json(await sagEngine.acknowledgeSpatialDirective(
      workspaceId, String(body.receiptId), body.acknowledgement ?? {},
    ));
  } catch (error) {
    return apiError(error);
  }
}
