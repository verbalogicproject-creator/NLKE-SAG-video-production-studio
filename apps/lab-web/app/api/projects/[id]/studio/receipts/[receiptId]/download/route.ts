import { sagEngine } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { studioTarget } from '@/lib/studio-target';
import { requireWorkspace } from '@/lib/workspace';

function fileStem(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 72) || 'sag-video';
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string; receiptId: string }> },
) {
  try {
    const { workspaceId } = await requireWorkspace();
    const { id, receiptId } = await params;
    const sequenceId = new URL(request.url).searchParams.get('sequence_id');
    const { project, sequence } = await studioTarget(id, workspaceId, sequenceId);
    const receipt = await sagEngine.receipt(workspaceId, receiptId);
    const payload = receipt.payload as {
      artifact_id?: string; artifact_sha256?: string; qc_report?: { passed?: boolean };
    } | undefined;
    const verified = (
      receipt.project_id === sequence.engineProjectId
      && receipt.command === 'render.verified'
      && receipt.status === 'observed_success'
      && payload?.artifact_id
      && payload?.artifact_sha256
      && payload?.qc_report?.passed === true
    );
    if (!verified) return Response.json({ error: 'verified_render_receipt_required' }, { status: 409 });
    return new Response(`${JSON.stringify(receipt, null, 2)}\n`, {
      status: 200,
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'content-disposition': `attachment; filename="${fileStem(project.name)}-r${receipt.project_revision}.receipt.json"`,
        'cache-control': 'private, no-store',
        'x-content-type-options': 'nosniff',
      },
    });
  } catch (error) {
    return apiError(error);
  }
}
