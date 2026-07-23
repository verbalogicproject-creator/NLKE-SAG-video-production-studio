import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { apiError, jsonSafe } from '@/lib/http';
import { reconcileChamberRun } from '@/lib/reconcile';
import { requireWorkspace } from '@/lib/workspace';

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    await reconcileChamberRun(id, workspaceId);
    const run = await db.chamberRun.findFirst({
      where: { id, project: { workspaceId } },
      include: { variants: { orderBy: { variant: 'asc' } }, project: true },
    });
    if (!run) return NextResponse.json({ error: 'chamber_run_not_found' }, { status: 404 });
    return NextResponse.json(jsonSafe({ run }));
  } catch (error) {
    return apiError(error);
  }
}
