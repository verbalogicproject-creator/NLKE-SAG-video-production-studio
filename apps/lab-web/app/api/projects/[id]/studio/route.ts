import { createHash, randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { sagEngine } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

async function studioTarget(id: string, workspaceId: string, sequenceId?: string | null) {
  const row = await db.project.findFirst({
    where: { id, workspaceId },
    include: { sequences: { where: { archivedAt: null }, orderBy: { createdAt: 'asc' } } },
  });
  if (!row) {
    throw Object.assign(new Error('Studio project is not initialized'), { status: 409, code: 'studio_not_initialized' });
  }
  const sequence = sequenceId
    ? row.sequences.find((entry) => entry.id === sequenceId)
    : row.sequences[0];
  if (!sequence) {
    throw Object.assign(new Error('Studio sequence was not found'), { status: 404, code: 'sequence_not_found' });
  }
  return { row, sequence };
}

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const sequenceId = new URL(request.url).searchParams.get('sequence_id');
    const { row, sequence } = await studioTarget(id, workspaceId, sequenceId);
    const [project, context, catalog, receipts, suggestions, spatial, delivery, production] = await Promise.all([
      sagEngine.project(workspaceId, sequence.engineProjectId),
      sagEngine.context(workspaceId, sequence.engineProjectId),
      sagEngine.activeCommands(workspaceId, sequence.engineProjectId),
      sagEngine.receipts(workspaceId, sequence.engineProjectId),
      sagEngine.suggestions(workspaceId, sequence.engineProjectId),
      sagEngine.spatialSnapshot(workspaceId, sequence.engineProjectId, { depth: 'context' }),
      sagEngine.deliveryState(workspaceId, sequence.engineProjectId),
      sagEngine.productionSession(workspaceId, sequence.engineProjectId),
    ]);
    return NextResponse.json({ controlProject: row, sequence, ...project, context, catalog, receipts, suggestions, spatial, delivery, production: production.production });
  } catch (error) {
    return apiError(error);
  }
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const body = await request.json();
    const { row, sequence } = await studioTarget(id, workspaceId, String(body.sequenceId ?? '') || null);
    const operation = String(body.operation ?? 'command');
    let result: Record<string, unknown>;

    if (operation === 'rename') {
      const name = String(body.name ?? '').trim();
      const sequenceName = String(body.sequenceName ?? '').trim();
      if (!name || name.length > 120 || !sequenceName || sequenceName.length > 120) {
        return NextResponse.json({ error: 'invalid_name', message: 'Project and sequence names must contain 1 to 120 characters.' }, { status: 422 });
      }
      const identityHash = createHash('sha256').update(`${name}\0${sequenceName}`).digest('hex').slice(0, 20);
      result = await sagEngine.command(
        workspaceId, sequence.engineProjectId, 'project.rename', { name }, Number(body.expectedRevision),
        `studio-rename-${Number(body.expectedRevision)}-${identityHash}`,
      );
      const fresh = await sagEngine.project(workspaceId, sequence.engineProjectId);
      const [updatedProject, updatedSequence] = await db.$transaction([
        db.project.update({ where: { id: row.id }, data: { name, engineRevision: fresh.project.revision } }),
        db.studioSequence.update({
          where: { id: sequence.id }, data: { name: sequenceName, currentRevision: fresh.project.revision },
        }),
      ]);
      return NextResponse.json({ result, project: fresh.project, controlProject: updatedProject, sequence: updatedSequence });
    }

    if (operation === 'command') {
      const arguments_ = (body.arguments ?? {}) as Record<string, unknown>;
      let confirmationId: string | undefined;
      if (body.confirm === true) {
        confirmationId = (await sagEngine.confirm(
          workspaceId, sequence.engineProjectId, String(body.command), arguments_, Number(body.expectedRevision),
        )).id;
      }
      result = await sagEngine.command(
        workspaceId, sequence.engineProjectId, String(body.command), arguments_,
        Number(body.expectedRevision), `studio-${randomUUID()}`, confirmationId,
      );
    } else if (operation === 'batch') {
      result = await sagEngine.batch(
        workspaceId, sequence.engineProjectId, body.commands ?? [], Number(body.expectedRevision),
        `studio-batch-${randomUUID()}`, body.confirmationId,
      );
    } else if (operation === 'propose') {
      result = await sagEngine.propose(workspaceId, sequence.engineProjectId, body.commands ?? [], Number(body.expectedRevision));
    } else if (operation === 'select') {
      result = await sagEngine.select(
        workspaceId, sequence.engineProjectId, body.itemIds ?? [], Number(body.expectedRevision), `studio-focus-${randomUUID()}`,
      );
    } else if (operation === 'pair') {
      result = await sagEngine.pair(workspaceId, sequence.engineProjectId);
    } else if (operation === 'pair_computer_use') {
      result = await sagEngine.pairComputerUse(workspaceId);
    } else if (operation === 'render') {
      result = await sagEngine.render(
        workspaceId,
        sequence.engineProjectId,
        Number(body.expectedRevision),
        `studio-render-${sequence.engineProjectId}-r${Number(body.expectedRevision)}`,
      );
    } else if (operation === 'analyze') {
      result = await sagEngine.suggestShorts(
        workspaceId, sequence.engineProjectId, Number(body.expectedRevision), String(body.assetId),
      );
    } else {
      return NextResponse.json({ error: 'unsupported_studio_operation' }, { status: 422 });
    }

    if (operation === 'command' || operation === 'batch') {
      const fresh = await sagEngine.project(workspaceId, sequence.engineProjectId);
      await db.$transaction([
        db.project.update({ where: { id: row.id }, data: { engineRevision: fresh.project.revision } }),
        db.studioSequence.update({ where: { id: sequence.id }, data: { currentRevision: fresh.project.revision } }),
      ]);
      return NextResponse.json({ result, project: fresh.project });
    }
    return NextResponse.json({ result });
  } catch (error) {
    return apiError(error);
  }
}
