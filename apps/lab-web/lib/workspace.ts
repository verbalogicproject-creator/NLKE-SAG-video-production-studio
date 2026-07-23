import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { db } from '@/lib/db';

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
    return { userId: user.id, workspaceId: workspace.id };
  }
  const session = await getServerSession(authOptions);
  const userId = (session?.user as { id?: string } | undefined)?.id;
  if (!userId) throw Object.assign(new Error('Authentication required'), { status: 401 });
  const membership = await db.workspaceMember.findFirst({ where: { userId }, orderBy: { joinedAt: 'asc' } });
  if (!membership) throw Object.assign(new Error('Workspace membership required'), { status: 403 });
  return { userId, workspaceId: membership.workspaceId };
}
