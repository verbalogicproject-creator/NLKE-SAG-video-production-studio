import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';
import { engineHeaders, sagEngineUrl } from '@/lib/engine';
import { studioEngineProject } from '@/lib/studio-target';

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id } = await params;
    const source = new URL(request.url);
    const cursor = source.searchParams.get('cursor') ?? '0';
    const engineProjectId = await studioEngineProject(id, workspaceId, source.searchParams.get('sequence_id'));
    const headers = new Headers(await engineHeaders(workspaceId, false));
    const lastEventId = request.headers.get('last-event-id');
    if (lastEventId) headers.set('last-event-id', lastEventId);
    const upstream = await fetch(
      `${sagEngineUrl()}/api/projects/${engineProjectId}/runtime/stream?cursor=${encodeURIComponent(cursor)}`,
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
