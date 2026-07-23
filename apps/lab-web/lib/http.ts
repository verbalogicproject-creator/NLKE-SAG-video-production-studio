import { NextResponse } from 'next/server';
import type { Prisma } from '@prisma/client';

export function apiError(error: unknown) {
  const value = error as { message?: string; status?: number; code?: string };
  return NextResponse.json(
    { error: value.code ?? 'request_failed', message: value.message ?? 'Request failed' },
    { status: value.status ?? 500 },
  );
}

export function jsonSafe<T>(value: T): T {
  return JSON.parse(JSON.stringify(value, (_key, item) => typeof item === 'bigint' ? item.toString() : item));
}

export function prismaJson(value: unknown): Prisma.InputJsonValue {
  return JSON.parse(JSON.stringify(value, (_key, item) => typeof item === 'bigint' ? item.toString() : item)) as Prisma.InputJsonValue;
}
