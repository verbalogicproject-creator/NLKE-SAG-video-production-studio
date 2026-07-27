import { NextResponse } from 'next/server';
import { engineHeaders, sagEngineUrl } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';
import { studioTarget } from '@/lib/studio-target';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string; assetId: string; kind: string }> },
) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id, assetId, kind } = await params;
    const { sequence } = await studioTarget(id, workspaceId, new URL(request.url).searchParams.get('sequence_id'));
    if (!['content', 'proxy', 'thumbnail'].includes(kind)) {
      return NextResponse.json({ error: 'invalid_asset_representation' }, { status: 422 });
    }
    const upstreamHeaders = new Headers(await engineHeaders(workspaceId, false));
    const range = request.headers.get('range');
    if (range) upstreamHeaders.set('range', range);
    const upstream = await fetch(
      `${sagEngineUrl()}/api/projects/${encodeURIComponent(sequence.engineProjectId)}/assets/${encodeURIComponent(assetId)}/${kind}`,
      { headers: upstreamHeaders, cache: 'no-store' },
    );
    if (!upstream.ok || !upstream.body) {
      return NextResponse.json({ error: 'asset_unavailable' }, { status: upstream.status });
    }
    const headers = new Headers();
    for (const name of ['content-type', 'content-length', 'content-range', 'etag', 'last-modified']) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    headers.set('cache-control', 'private, max-age=300');
    headers.set('accept-ranges', 'bytes');
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch (error) {
    return apiError(error);
  }
}
