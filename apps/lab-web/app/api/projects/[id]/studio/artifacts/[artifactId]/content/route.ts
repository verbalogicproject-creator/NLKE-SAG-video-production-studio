import { engineHeaders, sagEngine, sagEngineUrl } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { studioTarget } from '@/lib/studio-target';
import { requireWorkspace } from '@/lib/workspace';

function fileStem(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 72) || 'sag-video';
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string; artifactId: string }> },
) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id, artifactId } = await params;
    const sequenceId = new URL(request.url).searchParams.get('sequence_id');
    const { project, sequence } = await studioTarget(id, workspaceId, sequenceId);
    const [artifact, listed] = await Promise.all([
      sagEngine.artifact(workspaceId, artifactId),
      sagEngine.receipts(workspaceId, sequence.engineProjectId),
    ]);
    const receipt = listed.find((entry) => {
      const payload = entry.payload as {
        artifact_id?: string; artifact_sha256?: string; qc_report?: { passed?: boolean };
      } | undefined;
      return entry.project_id === sequence.engineProjectId
        && entry.command === 'render.verified'
        && entry.status === 'observed_success'
        && payload?.artifact_id === artifactId
        && payload?.artifact_sha256 === artifact.sha256
        && payload?.qc_report?.passed === true;
    });
    if (!receipt || artifact.project_id !== sequence.engineProjectId) {
      return Response.json({ error: 'verified_artifact_required' }, { status: 409 });
    }

    const upstream = await fetch(
      `${sagEngineUrl()}/api/artifacts/${encodeURIComponent(artifactId)}/content`,
      { headers: await engineHeaders(workspaceId, false), cache: 'no-store' },
    );
    if (!upstream.ok || !upstream.body) {
      return Response.json({ error: 'artifact_unavailable' }, { status: upstream.status });
    }
    const headers = new Headers();
    for (const name of ['content-type', 'content-length', 'etag', 'last-modified']) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    headers.set('content-disposition', `attachment; filename="${fileStem(project.name)}-r${receipt.project_revision}.mp4"`);
    headers.set('cache-control', 'private, no-store');
    headers.set('x-content-type-options', 'nosniff');
    headers.set('x-sag-artifact-sha256', artifact.sha256);
    return new Response(upstream.body, { status: 200, headers });
  } catch (error) {
    return apiError(error);
  }
}
