import { createHash, randomBytes } from 'node:crypto';
import { NextResponse } from 'next/server';
import { z } from 'zod';
import { db } from '@/lib/db';
import { apiError, jsonSafe } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

const ALLOWED_SCOPES = new Set(['projects:read', 'drafts:read', 'edits:write', 'renders:write', 'evidence:read', 'approvals:read', 'downloads:read', 'youtube:publish']);
const CreateSchema = z.object({
  name: z.string().trim().min(1).max(80),
  scopes: z.array(z.string()).min(1).max(8),
  expiresAt: z.coerce.date().optional(),
});

export async function GET() {
  try {
    const { workspaceId, role } = await requireWorkspace();
    if (role !== 'OWNER') return NextResponse.json({ error: 'owner_required' }, { status: 403 });
    const keys = await db.apiKey.findMany({
      where: { workspaceId },
      select: { id: true, name: true, prefix: true, scopes: true, status: true, expiresAt: true, lastUsedAt: true, createdAt: true },
      orderBy: { createdAt: 'desc' },
    });
    return NextResponse.json(jsonSafe({ keys }));
  } catch (error) { return apiError(error); }
}

export async function POST(request: Request) {
  try {
    const { workspaceId, userId, role } = await requireWorkspace();
    if (role !== 'OWNER') return NextResponse.json({ error: 'owner_required' }, { status: 403 });
    const input = CreateSchema.parse(await request.json());
    if (input.scopes.some((scope) => !ALLOWED_SCOPES.has(scope))) {
      return NextResponse.json({ error: 'invalid_scope' }, { status: 422 });
    }
    const secret = randomBytes(32).toString('base64url');
    const prefix = randomBytes(5).toString('hex');
    const rawKey = `sag_live_${prefix}_${secret}`;
    const key = await db.apiKey.create({ data: {
      workspaceId, createdById: userId, name: input.name, prefix,
      keyHash: createHash('sha256').update(rawKey, 'utf8').digest('hex'),
      scopes: [...new Set(input.scopes)], expiresAt: input.expiresAt,
    } });
    return NextResponse.json(jsonSafe({
      key: { id: key.id, name: key.name, prefix: key.prefix, scopes: key.scopes, expiresAt: key.expiresAt },
      secret: rawKey,
    }), { status: 201 });
  } catch (error) { return apiError(error); }
}
