import { notFound } from 'next/navigation';
import { db } from '@/lib/db';
import { jsonSafe } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';
import { ChamberProject } from '@/components/chamber/ChamberProject';

export const dynamic = 'force-dynamic';

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { workspaceId } = await requireWorkspace();
  const { id } = await params;
  const project = await db.project.findFirst({
    where: { id, workspaceId },
    include: { assets: true, chamberRuns: { include: { variants: true }, orderBy: { createdAt: 'desc' } } },
  });
  if (!project) notFound();
  return <ChamberProject project={jsonSafe(project) as any} />;
}
