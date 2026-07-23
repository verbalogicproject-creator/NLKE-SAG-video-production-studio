import { NextResponse } from 'next/server';

// GET /api/oauth/:platform/callback?code=…&state=…
// Exchanges code for tokens, AES-256-GCM encrypts with KMS key, stores in PlatformConnection.
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ platform: string }> },
) {
  const { platform } = await params;
  return NextResponse.json(
    {
      error: 'NotImplemented',
      message: `OAuth callback for ${platform}. Exchanges code, encrypts tokens with KMS, writes PlatformConnection row.`,
    },
    { status: 501 },
  );
}
