import { createHash } from 'node:crypto';
import { NextResponse } from 'next/server';
import { sagEngine } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { decryptSecret } from '@/lib/kms';
import { requireWorkspace } from '@/lib/workspace';

export async function POST(_: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId, role } = await requireWorkspace();
    if (role !== 'OWNER') return NextResponse.json({ error: 'owner_required' }, { status: 403 });
    const { id } = await params;
    const connection = await sagEngine.protectedProviderConnection(workspaceId, id);
    const aad = [workspaceId, connection.provider, connection.purpose, connection.display_name].join(':');
    const secret = await decryptSecret(String(connection.encrypted_secret), aad, 'connections');
    const fingerprint = createHash('sha256').update(secret, 'utf8').digest('hex').slice(0, 16);
    if (fingerprint !== connection.secret_fingerprint) {
      return NextResponse.json({ ok: false, error: 'secret_fingerprint_mismatch' }, { status: 409 });
    }
    return NextResponse.json({ ok: true, provider: connection.provider, purpose: connection.purpose, fingerprint });
  } catch (error) { return apiError(error); }
}

export async function DELETE(_: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { workspaceId, role } = await requireWorkspace();
    if (role !== 'OWNER') return NextResponse.json({ error: 'owner_required' }, { status: 403 });
    const { id } = await params;
    return NextResponse.json(await sagEngine.revokeProviderConnection(workspaceId, id));
  } catch (error) { return apiError(error); }
}
