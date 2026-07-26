import { db } from '@/lib/db';

export async function studioEngineProject(id: string, workspaceId: string) {
  const row = await db.project.findFirst({ where: { id, workspaceId } });
  if (!row?.engineProjectId) {
    throw Object.assign(new Error('Studio project is not initialized'), { status: 409 });
  }
  return row.engineProjectId;
}
