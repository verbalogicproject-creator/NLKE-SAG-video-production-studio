import { NextResponse } from 'next/server';
import { google } from 'googleapis';
import { db } from '@/lib/db';
import { apiError } from '@/lib/http';
import { encryptSecret } from '@/lib/kms';
import { verifyOAuthState } from '@/lib/oauth-state';
import { requireWorkspace } from '@/lib/workspace';

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const code = url.searchParams.get('code');
    const suppliedState = url.searchParams.get('state');
    const cookieState = request.headers.get('cookie')?.match(/(?:^|;\s*)sag_youtube_oauth_state=([^;]+)/)?.[1];
    if (!code || !suppliedState || !cookieState || decodeURIComponent(cookieState) !== suppliedState) {
      return NextResponse.json({ error: 'oauth_state_mismatch' }, { status: 400 });
    }
    const state = verifyOAuthState(suppliedState);
    const principal = await requireWorkspace();
    if (principal.userId !== state.userId || principal.workspaceId !== state.workspaceId) {
      return NextResponse.json({ error: 'oauth_principal_mismatch' }, { status: 403 });
    }
    const oauth = new google.auth.OAuth2(
      process.env.GOOGLE_CLIENT_ID,
      process.env.GOOGLE_CLIENT_SECRET,
      process.env.YOUTUBE_OAUTH_REDIRECT_URI,
    );
    const { tokens } = await oauth.getToken(code);
    oauth.setCredentials(tokens);
    const youtube = google.youtube({ version: 'v3', auth: oauth });
    const channels = await youtube.channels.list({ part: ['id', 'snippet'], mine: true });
    const channel = channels.data.items?.[0];
    if (!channel?.id || !tokens.access_token) throw new Error('YouTube did not return a channel and access token');
    const previous = await db.youTubeConnection.findUnique({ where: { workspaceId: state.workspaceId } });
    const aad = `youtube:${state.workspaceId}:${channel.id}`;
    await db.youTubeConnection.upsert({
      where: { workspaceId: state.workspaceId },
      update: {
        channelId: channel.id,
        channelTitle: channel.snippet?.title,
        encryptedAccessToken: await encryptSecret(tokens.access_token, aad),
        encryptedRefreshToken: tokens.refresh_token ? await encryptSecret(tokens.refresh_token, aad) : previous?.encryptedRefreshToken,
        expiresAt: tokens.expiry_date ? new Date(tokens.expiry_date) : null,
        scopes: tokens.scope?.split(' ') ?? [],
        kmsKeyVersion: process.env.YOUTUBE_KMS_KEY!,
      },
      create: {
        workspaceId: state.workspaceId,
        channelId: channel.id,
        channelTitle: channel.snippet?.title,
        encryptedAccessToken: await encryptSecret(tokens.access_token, aad),
        encryptedRefreshToken: tokens.refresh_token ? await encryptSecret(tokens.refresh_token, aad) : null,
        expiresAt: tokens.expiry_date ? new Date(tokens.expiry_date) : null,
        scopes: tokens.scope?.split(' ') ?? [],
        kmsKeyVersion: process.env.YOUTUBE_KMS_KEY!,
      },
    });
    const response = NextResponse.redirect(new URL('/dashboard?youtube=connected', request.url));
    response.cookies.delete('sag_youtube_oauth_state');
    return response;
  } catch (error) { return apiError(error); }
}
