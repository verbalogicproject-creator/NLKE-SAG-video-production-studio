import { NextResponse } from 'next/server';
import { google } from 'googleapis';
import { createOAuthState } from '@/lib/oauth-state';
import { apiError } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

export async function GET() {
  try {
    const { workspaceId, userId, role } = await requireWorkspace();
    if (role !== 'OWNER' && role !== 'ADMIN') return NextResponse.json({ error: 'admin_required' }, { status: 403 });
    const state = createOAuthState(userId, workspaceId);
    const oauth = new google.auth.OAuth2(
      process.env.GOOGLE_CLIENT_ID,
      process.env.GOOGLE_CLIENT_SECRET,
      process.env.YOUTUBE_OAUTH_REDIRECT_URI,
    );
    const url = oauth.generateAuthUrl({
      access_type: 'offline',
      prompt: 'consent',
      include_granted_scopes: true,
      state,
      scope: ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly'],
    });
    const response = NextResponse.redirect(url);
    response.cookies.set('sag_youtube_oauth_state', state, {
      httpOnly: true, sameSite: 'lax', secure: process.env.NODE_ENV === 'production', path: '/api/oauth/youtube/callback', maxAge: 600,
    });
    return response;
  } catch (error) { return apiError(error); }
}
