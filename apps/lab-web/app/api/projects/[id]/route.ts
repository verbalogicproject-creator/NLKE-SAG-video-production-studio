import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { apiError, jsonSafe } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const project = await db.project.findFirst({
      where: { id, workspaceId },
      include: {
        assets: true,
        chamberRuns: { include: { variants: true }, orderBy: { createdAt: 'desc' } },
      },
    });
    if (!project) return NextResponse.json({ error: 'project_not_found' }, { status: 404 });
    return NextResponse.json(jsonSafe({ project }));
  } catch (error) {
    return apiError(error);
  }
}
