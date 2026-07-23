import Link from 'next/link';
import { db } from '@/lib/db';
import { requireWorkspace } from '@/lib/workspace';
import { PanelShell } from '@/components/lab/PanelShell';
import { NewProjectButton } from '@/components/chamber/NewProjectButton';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Chamber Dashboard' };

export default async function DashboardPage() {
  const { workspaceId } = await requireWorkspace();
  const projects = await db.project.findMany({
    where: { workspaceId },
    include: { assets: true, chamberRuns: { orderBy: { createdAt: 'desc' }, take: 1 } },
    orderBy: { updatedAt: 'desc' },
  });
  return <div className="min-h-[calc(100vh-3rem)] p-4">
    <div className="flex items-center justify-between border-b border-border-base pb-3 mb-4">
      <div><h1 className="font-display text-2xl text-ink-0">The Chamber</h1><p className="data text-[11px] text-ink-2">{projects.length} PROJECTS · VERIFIED OUTPUT ONLY</p></div>
      <NewProjectButton />
    </div>
    {projects.length === 0 ? <div className="border border-dashed border-border-base p-10 text-center text-ink-2">Create a project, upload a video, and put it in the Chamber.</div> : null}
    <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-2">
      {projects.map((project) => {
        const run = project.chamberRuns[0];
        return <Link href={`/projects/${project.id}`} key={project.id}>
          <PanelShell title={project.status} subtitle={project.name} footer={<><span>{project.assets.length} ASSETS</span><span className="text-amber">OPEN →</span></>}>
            <div className="p-4 min-h-28">
              <div className="data text-[10px] text-ink-3">CHAMBER STATE</div>
              <div className="mt-2 font-display text-lg text-ink-0">{run?.status ?? 'NOT STARTED'}</div>
              <div className="mt-3 h-1 bg-border-base"><div className="h-full bg-amber" style={{ width: run?.status === 'READY_TO_PUBLISH' ? '100%' : run ? '45%' : '0%' }} /></div>
            </div>
          </PanelShell>
        </Link>;
      })}
    </div>
  </div>;
}
