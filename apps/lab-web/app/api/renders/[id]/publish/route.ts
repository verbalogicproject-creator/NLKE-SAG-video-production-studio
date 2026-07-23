import { NextResponse } from 'next/server';

// POST /api/renders/:id/publish
// Body: { platforms: ['YOUTUBE', 'LINKEDIN', ...] }
// Side-effect: enqueues job.publish; creates PlatformPublication rows PENDING.
export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return NextResponse.json(
    {
      error: 'NotImplemented',
      message: `Enqueues job.publish for render ${id}. Validates render is COMPLETED and each platform is connected.`,
    },
    { status: 501 },
  );
}
