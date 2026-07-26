import { createHash } from 'node:crypto';
import { NextResponse } from 'next/server';
import { z } from 'zod';
import { sagEngine } from '@/lib/engine';
import { apiError } from '@/lib/http';
import { encryptSecret, kmsKeyName } from '@/lib/kms';
import { requireWorkspace } from '@/lib/workspace';

const ConnectionSchema = z.object({
  provider: z.string().regex(/^[a-z][a-z0-9_.-]{1,63}$/),
  purpose: z.string().regex(/^[a-z][a-z0-9_.-]{1,63}$/),
  displayName: z.string().trim().min(1).max(80),
  scopes: z.array(z.string().regex(/^[a-zA-Z0-9:._/-]{1,120}$/)).max(32).default([]),
  secret: z.string().min(1).max(65536),
  metadata: z.record(z.unknown()).default({}),
});

function requireOwner(role: string) {
  if (role !== 'OWNER') throw Object.assign(new Error('Owner access required'), { status: 403 });
}

export async function GET() {
  try {
    const { workspaceId, role } = await requireWorkspace();
    requireOwner(role);
    return NextResponse.json(await sagEngine.providerConnections(workspaceId));
  } catch (error) { return apiError(error); }
}

export async function POST(request: Request) {
  try {
    const { workspaceId, role } = await requireWorkspace();
    requireOwner(role);
    const input = ConnectionSchema.parse(await request.json());
    const aad = [workspaceId, input.provider, input.purpose, input.displayName].join(':');
    const encryptedSecret = await encryptSecret(input.secret, aad, 'connections');
    const connection = await sagEngine.putProviderConnection(workspaceId, {
      provider: input.provider, purpose: input.purpose, display_name: input.displayName,
      scopes: [...new Set(input.scopes)], encrypted_secret: encryptedSecret,
      kms_key_version: kmsKeyName('connections'),
      secret_fingerprint: createHash('sha256').update(input.secret, 'utf8').digest('hex').slice(0, 16),
      metadata: input.metadata,
    });
    return NextResponse.json(connection, { status: 201 });
  } catch (error) { return apiError(error); }
}
