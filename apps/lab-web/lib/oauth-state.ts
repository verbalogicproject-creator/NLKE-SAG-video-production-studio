import { createHmac, randomBytes, timingSafeEqual } from 'node:crypto';

type State = { nonce: string; userId: string; workspaceId: string; expiresAt: number };

function secret(): string {
  const value = process.env.NEXTAUTH_SECRET;
  if (!value) throw new Error('NEXTAUTH_SECRET is required');
  return value;
}

export function createOAuthState(userId: string, workspaceId: string): string {
  const body = Buffer.from(JSON.stringify({
    nonce: randomBytes(24).toString('base64url'), userId, workspaceId, expiresAt: Date.now() + 10 * 60_000,
  } satisfies State)).toString('base64url');
  const signature = createHmac('sha256', secret()).update(body).digest('base64url');
  return `${body}.${signature}`;
}

export function verifyOAuthState(value: string): State {
  const [body, signature] = value.split('.');
  if (!body || !signature) throw Object.assign(new Error('invalid OAuth state'), { status: 400 });
  const expected = createHmac('sha256', secret()).update(body).digest();
  const actual = Buffer.from(signature, 'base64url');
  if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) {
    throw Object.assign(new Error('invalid OAuth state signature'), { status: 400 });
  }
  const state = JSON.parse(Buffer.from(body, 'base64url').toString('utf8')) as State;
  if (!state.nonce || !state.userId || !state.workspaceId || state.expiresAt <= Date.now()) {
    throw Object.assign(new Error('expired OAuth state'), { status: 400 });
  }
  return state;
}
