import { NextResponse } from 'next/server';

// POST /api/projects/:id/assets/upload-url
// Body: { filename, contentType, sizeBytes }
// Returns: { assetId, url, expiresAt }
export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return NextResponse.json(
    {
      error: 'NotImplemented',
      message: `Issues R2 presigned PUT URL for project ${id}. Uses lib/r2.ts presignUpload.`,
    },
    { status: 501 },
  );
}
