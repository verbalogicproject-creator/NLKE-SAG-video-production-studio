import type { NextAuthOptions } from 'next-auth';
import GoogleProvider from 'next-auth/providers/google';
import { PrismaAdapter } from '@auth/prisma-adapter';
import { db } from '@/lib/db';

/**
 * Auth.js v4 config. The critical line is `cookies.sessionToken.options.domain`
 * which MUST be `.verbalogix.com` in production so the session is readable
 * from both the marketing site (verbalogix.com) and the lab (lab.verbalogix.com).
 *
 * In development we leave the cookie domain unset so localhost sessions work.
 */
export const authOptions: NextAuthOptions = {
  adapter: PrismaAdapter(db),
  session: { strategy: 'database' },
  providers: [
    GoogleProvider({
      clientId:     process.env.GOOGLE_CLIENT_ID     ?? '',
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? '',
      authorization: {
        params: {
          prompt: 'select_account',
          access_type: 'offline',
          response_type: 'code',
        },
      },
    }),
  ],
  pages: {
    signIn: '/login',
  },
  cookies: isProd()
    ? {
        sessionToken: {
          name: '__Secure-next-auth.session-token',
          options: {
            httpOnly: true,
            sameSite: 'lax',
            path: '/',
            secure: true,
            domain: process.env.NEXTAUTH_COOKIE_DOMAIN ?? '.verbalogix.com',
          },
        },
      }
    : undefined,
  callbacks: {
    async signIn({ user, account, profile }) {
      if (account?.provider !== 'google' || !user.email || !user.id) return false;
      if ((profile as { email_verified?: boolean } | undefined)?.email_verified === false) return false;
      const email = user.email.trim().toLowerCase();
      const existing = await db.workspaceMember.findFirst({ where: { userId: user.id } });
      if (existing) return true;
      const invitation = await db.invitation.findFirst({
        where: { email, status: 'PENDING', expiresAt: { gt: new Date() } },
        orderBy: { createdAt: 'asc' },
      });
      if (!invitation) return false;
      await db.$transaction([
        db.user.update({ where: { id: user.id }, data: { email } }),
        db.workspaceMember.upsert({
          where: { userId_workspaceId: { userId: user.id, workspaceId: invitation.workspaceId } },
          update: { role: invitation.role },
          create: { userId: user.id, workspaceId: invitation.workspaceId, role: invitation.role },
        }),
        db.invitation.update({ where: { id: invitation.id }, data: { status: 'ACCEPTED', acceptedAt: new Date() } }),
      ]);
      return true;
    },
    async session({ session, user }) {
      if (session.user && user?.id) {
        (session.user as { id?: string }).id = user.id;
      }
      return session;
    },
  },
};

function isProd(): boolean {
  return process.env.NODE_ENV === 'production';
}
