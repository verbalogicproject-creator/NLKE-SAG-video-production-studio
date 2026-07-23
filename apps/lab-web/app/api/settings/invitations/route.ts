import { NextResponse } from 'next/server';
import { z } from 'zod';
import { db } from '@/lib/db';
import { apiError, jsonSafe } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

const CreateSchema = z.object({
  email: z.string().email().transform((value) => value.trim().toLowerCase()),
  role: z.enum(['ADMIN', 'EDITOR', 'VIEWER']).default('EDITOR'),
  expiresInDays: z.number().int().min(1).max(30).default(7),
});

export async function POST(request: Request) {
  try {
    const { workspaceId, role } = await requireWorkspace();
    if (role !== 'OWNER' && role !== 'ADMIN') return NextResponse.json({ error: 'admin_required' }, { status: 403 });
    const input = CreateSchema.parse(await request.json());
    const invitation = await db.invitation.upsert({
      where: { workspaceId_email: { workspaceId, email: input.email } },
      update: { role: input.role, status: 'PENDING', expiresAt: new Date(Date.now() + input.expiresInDays * 86_400_000), acceptedAt: null },
      create: { workspaceId, email: input.email, role: input.role, expiresAt: new Date(Date.now() + input.expiresInDays * 86_400_000) },
    });
    return NextResponse.json(jsonSafe({ invitation }), { status: 201 });
  } catch (error) { return apiError(error); }
}
