import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { sagEngine } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

async function studioProject(id: string, workspaceId: string) {
  const row = await db.project.findFirst({ where: { id, workspaceId } });
  if (!row?.engineProjectId) {
    throw Object.assign(new Error('Studio project is not initialized'), { status: 409, code: 'studio_not_initialized' });
  }
  return row;
}

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const row = await studioProject(id, workspaceId);
    const [project, context, catalog, receipts, suggestions, spatial, delivery] = await Promise.all([
      sagEngine.project(workspaceId, row.engineProjectId!),
      sagEngine.context(workspaceId, row.engineProjectId!),
      sagEngine.activeCommands(workspaceId, row.engineProjectId!),
      sagEngine.receipts(workspaceId, row.engineProjectId!),
      sagEngine.suggestions(workspaceId, row.engineProjectId!),
      sagEngine.spatialSnapshot(workspaceId, row.engineProjectId!, { depth: 'context' }),
      sagEngine.deliveryState(workspaceId, row.engineProjectId!),
    ]);
    return NextResponse.json({ controlProject: row, ...project, context, catalog, receipts, suggestions, spatial, delivery });
  } catch (error) {
    return apiError(error);
  }
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const row = await studioProject(id, workspaceId);
    const body = await request.json();
    const operation = String(body.operation ?? 'command');
    let result: Record<string, unknown>;

    if (operation === 'command') {
      const arguments_ = (body.arguments ?? {}) as Record<string, unknown>;
      let confirmationId: string | undefined;
      if (body.confirm === true) {
        confirmationId = (await sagEngine.confirm(
          workspaceId, row.engineProjectId!, String(body.command), arguments_, Number(body.expectedRevision),
        )).id;
      }
      result = await sagEngine.command(
        workspaceId, row.engineProjectId!, String(body.command), arguments_,
        Number(body.expectedRevision), `studio-${randomUUID()}`, confirmationId,
      );
    } else if (operation === 'batch') {
      result = await sagEngine.batch(
        workspaceId, row.engineProjectId!, body.commands ?? [], Number(body.expectedRevision),
        `studio-batch-${randomUUID()}`, body.confirmationId,
      );
    } else if (operation === 'propose') {
      result = await sagEngine.propose(workspaceId, row.engineProjectId!, body.commands ?? [], Number(body.expectedRevision));
    } else if (operation === 'select') {
      result = await sagEngine.select(
        workspaceId, row.engineProjectId!, body.itemIds ?? [], Number(body.expectedRevision), `studio-focus-${randomUUID()}`,
      );
    } else if (operation === 'pair') {
      result = await sagEngine.pair(workspaceId, row.engineProjectId!);
    } else if (operation === 'render') {
      result = await sagEngine.render(
        workspaceId, row.engineProjectId!, Number(body.expectedRevision), `studio-render-${randomUUID()}`,
      );
    } else if (operation === 'analyze') {
      result = await sagEngine.suggestShorts(
        workspaceId, row.engineProjectId!, Number(body.expectedRevision), String(body.assetId),
      );
    } else {
      return NextResponse.json({ error: 'unsupported_studio_operation' }, { status: 422 });
    }

    if (operation === 'command' || operation === 'batch') {
      const fresh = await sagEngine.project(workspaceId, row.engineProjectId!);
      await db.$transaction([
        db.project.update({ where: { id: row.id }, data: { engineRevision: fresh.project.revision } }),
        db.studioSequence.updateMany({
          where: { projectId: row.id, engineProjectId: row.engineProjectId! },
          data: { currentRevision: fresh.project.revision },
        }),
      ]);
      return NextResponse.json({ result, project: fresh.project });
    }
    return NextResponse.json({ result });
  } catch (error) {
    return apiError(error);
  }
}
