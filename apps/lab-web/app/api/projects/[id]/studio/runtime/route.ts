import { db } from '@/lib/db';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';
import { engineHeaders, sagEngineUrl } from '@/lib/engine';

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const row = await db.project.findFirst({ where: { id, workspaceId } });
    if (!row?.engineProjectId) return new Response('Studio project is not initialized', { status: 409 });
    const source = new URL(request.url);
    const cursor = source.searchParams.get('cursor') ?? '0';
    const headers = new Headers(await engineHeaders(workspaceId, false));
    const lastEventId = request.headers.get('last-event-id');
    if (lastEventId) headers.set('last-event-id', lastEventId);
    const upstream = await fetch(
      `${sagEngineUrl()}/api/projects/${row.engineProjectId}/runtime/stream?cursor=${encodeURIComponent(cursor)}`,
      { headers, cache: 'no-store', signal: request.signal },
    );
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        'content-type': upstream.headers.get('content-type') ?? 'text/event-stream',
        'cache-control': 'no-cache, no-transform',
        connection: 'keep-alive',
        'x-accel-buffering': 'no',
      },
    });
  } catch (error) {
    return apiError(error);
  }
}
