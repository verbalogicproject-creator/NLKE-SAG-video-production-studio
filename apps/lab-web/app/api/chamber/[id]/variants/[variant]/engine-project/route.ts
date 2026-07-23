import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { VerticalVariantSchema } from '@verbalogix/media-contracts';
import { db } from '@/lib/db';
import { sagEngine } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

async function context(id: string, rawVariant: string, workspaceId: string) {
  const variant = VerticalVariantSchema.parse(rawVariant);
  const row = await db.chamberVariant.findFirst({
    where: { chamberRunId: id, variant, chamberRun: { project: { workspaceId } } },
  });
  if (!row?.engineProjectId) throw Object.assign(new Error('Draft is not accepted'), { status: 409, code: 'draft_not_accepted' });
  return row;
}

export async function GET(_request: Request, { params }: { params: Promise<{ id: string; variant: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id, variant } = await params;
    const row = await context(id, variant, workspaceId);
    return NextResponse.json(await sagEngine.project(workspaceId, row.engineProjectId!));
  } catch (error) {
    return apiError(error);
  }
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string; variant: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id, variant } = await params;
    const row = await context(id, variant, workspaceId);
    const body = await request.json();
    const receipt = await sagEngine.command(
      workspaceId,
      row.engineProjectId!,
      String(body.command),
      body.arguments ?? {},
      Number(body.expectedRevision),
      `lab-edit-${randomUUID()}`,
    );
    const project = await sagEngine.project(workspaceId, row.engineProjectId!);
    await db.chamberVariant.update({ where: { id: row.id }, data: { engineRevision: project.project.revision, status: 'ACCEPTED' } });
    return NextResponse.json({ receipt, project: project.project });
  } catch (error) {
    return apiError(error);
  }
}
