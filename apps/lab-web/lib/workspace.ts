import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { db } from '@/lib/db';
import { createHash } from 'node:crypto';

export async function requireWorkspace() {
  if (process.env.VERBALOGIX_LOCAL_DEV === '1') {
    const user = await db.user.upsert({
      where: { email: 'local@verbalogix.test' },
      update: {},
      create: { email: 'local@verbalogix.test', name: 'Local Operator' },
    });
    const workspace = await db.workspace.upsert({
      where: { slug: 'local-chamber' },
      update: {},
      create: { name: 'Local Chamber', slug: 'local-chamber', members: { create: { userId: user.id, role: 'OWNER' } } },
    });
    return { userId: user.id, workspaceId: workspace.id, role: 'OWNER' as const };
  }
  const session = await getServerSession(authOptions);
  const userId = (session?.user as { id?: string } | undefined)?.id;
  if (!userId) throw Object.assign(new Error('Authentication required'), { status: 401 });
  const membership = await db.workspaceMember.findFirst({ where: { userId }, orderBy: { joinedAt: 'asc' } });
  if (!membership) throw Object.assign(new Error('Workspace membership required'), { status: 403 });
  return { userId, workspaceId: membership.workspaceId, role: membership.role };
}

export async function requireApiKey(request: Request, requiredScopes: string[] = []) {
  const authorization = request.headers.get('authorization') ?? '';
  const raw = authorization.startsWith('Bearer ') ? authorization.slice(7).trim() : '';
  if (!raw) throw Object.assign(new Error('API key required'), { status: 401, code: 'api_key_required' });
  const keyHash = createHash('sha256').update(raw, 'utf8').digest('hex');
  const key = await db.apiKey.findUnique({ where: { keyHash } });
  if (!key || key.status !== 'ACTIVE' || (key.expiresAt && key.expiresAt <= new Date())) {
    throw Object.assign(new Error('API key is invalid or expired'), { status: 401, code: 'invalid_api_key' });
  }
  if (requiredScopes.some((scope) => !key.scopes.includes(scope) && !key.scopes.includes('*'))) {
    throw Object.assign(new Error('API key lacks the required scope'), { status: 403, code: 'insufficient_scope' });
  }
  await db.apiKey.update({ where: { id: key.id }, data: { lastUsedAt: new Date() } });
  return { apiKeyId: key.id, workspaceId: key.workspaceId, scopes: key.scopes };
}
