import { notFound, redirect } from 'next/navigation';
import { db } from '@/lib/db';
import { requireWorkspace } from '@/lib/workspace';

export const dynamic = 'force-dynamic';

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { workspaceId } = await requireWorkspace();
  const { id } = await params;
  const project = await db.project.findFirst({
    where: { id, workspaceId },
    include: {
      assets: true,
      sequences: { where: { archivedAt: null }, orderBy: { createdAt: 'asc' }, take: 1 },
      chamberRuns: { include: { variants: true }, orderBy: { createdAt: 'desc' } },
    },
  });
  if (!project) notFound();
  if (project.sequences[0]) redirect(`/projects/${project.id}/studio/${project.sequences[0].id}`);
  return null;
}
