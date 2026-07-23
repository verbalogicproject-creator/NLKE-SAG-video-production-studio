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
