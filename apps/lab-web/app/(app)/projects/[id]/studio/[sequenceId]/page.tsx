import { notFound } from 'next/navigation';
import { db } from '@/lib/db';
import { jsonSafe } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';
import { sagEngine } from '@/lib/engine';
import { Studio } from '@/components/studio/Studio';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Studio' };

export default async function StudioPage({ params }: { params: Promise<{ id: string; sequenceId: string }> }) {
  const { workspaceId } = await requireWorkspace();
  const { id, sequenceId } = await params;
  const controlProject = await db.project.findFirst({
    where: { id, workspaceId },
    include: {
      sequences: {
        where: { id: sequenceId, archivedAt: null },
      },
    },
  });
  const sequence = controlProject?.sequences[0];
  if (!controlProject || !sequence) notFound();
  const [project, context, catalog, receipts, spatial, delivery, production] = await Promise.all([
    sagEngine.project(workspaceId, sequence.engineProjectId),
    sagEngine.context(workspaceId, sequence.engineProjectId),
    sagEngine.activeCommands(workspaceId, sequence.engineProjectId),
    sagEngine.receipts(workspaceId, sequence.engineProjectId),
    sagEngine.spatialSnapshot(workspaceId, sequence.engineProjectId, { depth: 'context' }),
    sagEngine.deliveryState(workspaceId, sequence.engineProjectId),
    sagEngine.productionSession(workspaceId, sequence.engineProjectId),
  ]);
  return <Studio
    controlProject={jsonSafe(controlProject) as any}
    initialProject={project.project as any}
    initialContext={context as any}
    initialCatalog={catalog as any}
    initialReceipts={(receipts as any).receipts ?? receipts}
    initialSpatial={spatial as any}
    initialDelivery={delivery as any}
    initialProduction={production.production}
  />;
}
