import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { sagEngine } from '@/lib/engine';
import { apiError, jsonSafe } from '@/lib/http';
import { requireWorkspace } from '@/lib/workspace';

export async function GET() {
  try {
    const { workspaceId } = await requireWorkspace();
    const projects = await db.project.findMany({
      where: { workspaceId },
      include: { assets: true, chamberRuns: { orderBy: { createdAt: 'desc' }, take: 1 } },
      orderBy: { updatedAt: 'desc' },
    });
    return NextResponse.json(jsonSafe({ projects }));
  } catch (error) {
    return apiError(error);
  }
}

export async function POST(request: Request) {
  try {
    const { workspaceId } = await requireWorkspace();
    const body = await request.json();
    const name = String(body.name ?? '').trim();
    if (!name || name.length > 120) return NextResponse.json({ error: 'invalid_name' }, { status: 422 });
    const preset = String(body.preset ?? 'landscape_1080p');
    if (!['landscape_1080p', 'vertical_1080p', 'preview_540p'].includes(preset)) {
      return NextResponse.json({ error: 'invalid_canvas_preset' }, { status: 422 });
    }
    const engine = await sagEngine.createProject(
      workspaceId, name,
      preset as 'landscape_1080p' | 'vertical_1080p' | 'preview_540p',
    );
    const project = await db.project.create({
      data: {
        workspaceId,
        name,
        description: body.description ? String(body.description).slice(0, 5000) : null,
        engineProjectId: engine.project.id,
        engineRevision: engine.project.revision,
        status: 'DRAFT',
        sequences: {
          create: {
            engineProjectId: engine.project.id,
            name: `${name} master`,
            currentRevision: engine.project.revision,
            deliveryProfiles: {
              create: [
                { destination: 'youtube_shorts', aspectRatio: '9:16', width: 1080, height: 1920 },
                { destination: 'tiktok', aspectRatio: '9:16', width: 1080, height: 1920 },
                { destination: 'instagram_reels', aspectRatio: '9:16', width: 1080, height: 1920 },
              ],
            },
          },
        },
      },
      include: { sequences: { include: { deliveryProfiles: true } } },
    });
    return NextResponse.json(jsonSafe({ project }), { status: 201 });
  } catch (error) {
    return apiError(error);
  }
}
