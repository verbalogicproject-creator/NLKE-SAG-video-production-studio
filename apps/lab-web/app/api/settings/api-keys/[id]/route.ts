import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId, role } = await requireWorkspace();
    if (role !== 'OWNER') return NextResponse.json({ error: 'owner_required' }, { status: 403 });
    const { id } = await params;
    const result = await db.apiKey.updateMany({ where: { id, workspaceId, status: 'ACTIVE' }, data: { status: 'REVOKED' } });
    if (!result.count) return NextResponse.json({ error: 'api_key_not_found' }, { status: 404 });
    return new NextResponse(null, { status: 204 });
  } catch (error) { return apiError(error); }
}
