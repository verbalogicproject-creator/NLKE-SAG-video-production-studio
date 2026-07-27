import { db } from '@/lib/db';

export async function studioTarget(id: string, workspaceId: string, sequenceId?: string | null) {
  const project = await db.project.findFirst({
    where: { id, workspaceId },
    include: { sequences: { where: { archivedAt: null }, orderBy: { createdAt: 'asc' } } },
  });
  if (!project) {
    throw Object.assign(new Error('Studio project is not initialized'), { status: 409 });
  }
  const sequence = sequenceId
    ? project.sequences.find((entry) => entry.id === sequenceId)
    : project.sequences[0];
  if (!sequence) throw Object.assign(new Error('Studio sequence was not found'), { status: 404 });
  return { project, sequence };
}

export async function studioEngineProject(id: string, workspaceId: string, sequenceId?: string | null) {
  return (await studioTarget(id, workspaceId, sequenceId)).sequence.engineProjectId;
}
