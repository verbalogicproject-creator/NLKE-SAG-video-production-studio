import { NextResponse } from 'next/server';
import { sagEngine } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';
import { studioTarget } from '@/lib/studio-target';

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; compositeId: string }> },
) {
  try {
    const { workspaceId, userId } = await requireWorkspace();
    const { id, compositeId } = await params;
    const { sequence } = await studioTarget(id, workspaceId, new URL(request.url).searchParams.get('sequence_id'));
    const body = await request.json() as { decision?: string; note?: string };
    if (!['approved', 'rejected'].includes(String(body.decision))) {
      return NextResponse.json({ error: 'invalid_protected_composite_decision' }, { status: 422 });
    }
    return NextResponse.json(await sagEngine.decideProtectedScreenComposite(
      workspaceId, sequence.engineProjectId, compositeId,
      {
        decision: body.decision as 'approved' | 'rejected',
        actor: `studio:${userId}`,
        note: body.note,
      },
    ));
  } catch (error) {
    return apiError(error);
  }
}
