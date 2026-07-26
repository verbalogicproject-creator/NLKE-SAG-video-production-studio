import { db } from '@/lib/db';
import type { DirectorInput } from '@/lib/engine';

export async function repoVideoEngineProject(controlProjectId: string, sequenceId: string, workspaceId: string) {
  if (!sequenceId) throw Object.assign(new Error('Studio sequence is required'), { status: 400, code: 'sequence_required' });
  const project = await db.project.findFirst({
    where: { id: controlProjectId, workspaceId },
    include: { sequences: { where: { id: sequenceId, archivedAt: null }, take: 1 } },
  });
  const sequence = project?.sequences[0];
  if (!project || !sequence) throw Object.assign(new Error('Studio sequence was not found'), { status: 404, code: 'sequence_not_found' });
  return sequence.engineProjectId;
}

export function directorInput(body: Record<string, unknown>): DirectorInput {
  return {
    repository_url: String(body.repository_url ?? ''),
    ref: String(body.ref ?? ''),
    creative_instructions: String(body.creative_instructions ?? ''),
    audience: String(body.audience ?? ''),
    goal: String(body.goal ?? ''),
    duration_seconds: Number(body.duration_seconds ?? 60),
    visual_style: String(body.visual_style ?? ''),
    target_platform: String(body.target_platform ?? 'youtube_shorts'),
    brand_kit: String(body.brand_kit ?? ''),
    reference_assets: Array.isArray(body.reference_assets) ? body.reference_assets.map(String) : [],
  };
}

export function requireHumanConfirmation(request: Request, body: Record<string, unknown>) {
  const confirmationId = String(body.confirmation_id ?? '');
  const supplied = request.headers.get('x-sag-human-confirmation') ?? '';
  if (confirmationId.length < 8 || supplied !== confirmationId) {
    throw Object.assign(new Error('A fresh human confirmation is required'), { status: 403, code: 'human_confirmation_required' });
  }
}
