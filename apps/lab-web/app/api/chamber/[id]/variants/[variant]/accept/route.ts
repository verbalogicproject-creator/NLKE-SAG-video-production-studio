import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { VerticalVariantSchema } from '@verbalogix/media-contracts';
import { db } from '@/lib/db';
import { sagEngine } from '@/lib/engine';
import { apiError, jsonSafe } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

export async function POST(request: Request, { params }: { params: Promise<{ id: string; variant: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id, variant: rawVariant } = await params;
    const variant = VerticalVariantSchema.parse(rawVariant);
    const body = await request.json().catch(() => ({}));
    const row = await db.chamberVariant.findFirst({
      where: { chamberRunId: id, variant, chamberRun: { project: { workspaceId } } },
      include: { chamberRun: true },
    });
    if (!row?.suggestionId) return NextResponse.json({ error: 'draft_not_ready' }, { status: 409 });
    if (row.status === 'HALTED_BRAND_VIOLATION') return NextResponse.json({ error: 'brand_violation' }, { status: 409 });
    if (row.engineProjectId) return NextResponse.json(jsonSafe({ variant: row }));
    const accepted = await sagEngine.accept(
      workspaceId,
      row.suggestionId,
      `chamber-accept-${id}-${variant}-${randomUUID()}`,
      body.name ? String(body.name).slice(0, 120) : `${variant} draft`,
    );
    const updated = await db.chamberVariant.update({
      where: { id: row.id },
      data: { engineProjectId: accepted.project.id, engineRevision: accepted.project.revision, receiptId: accepted.receipt.id, status: 'ACCEPTED' },
    });
    await db.chamberRun.update({ where: { id }, data: { status: 'IN_REVIEW' } });
    return NextResponse.json(jsonSafe({ variant: updated, accepted }));
  } catch (error) {
    return apiError(error);
  }
}
