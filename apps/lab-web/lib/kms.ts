import { GoogleAuth } from 'google-auth-library';

const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });

export function kmsKeyName(purpose: 'youtube' | 'connections' = 'youtube'): string {
  const value = purpose === 'connections'
    ? process.env.SAG_CONNECTIONS_KMS_KEY ?? process.env.YOUTUBE_KMS_KEY
    : process.env.YOUTUBE_KMS_KEY;
  if (!value) throw new Error(`${purpose === 'connections' ? 'SAG_CONNECTIONS_KMS_KEY' : 'YOUTUBE_KMS_KEY'} is required`);
  return value;
}

export async function encryptSecret(plaintext: string, aad: string, purpose: 'youtube' | 'connections' = 'youtube'): Promise<string> {
  const client = await auth.getClient();
  const response = await client.request<{ ciphertext: string }>({
    url: `https://cloudkms.googleapis.com/v1/${kmsKeyName(purpose)}:encrypt`,
    method: 'POST',
    data: {
      plaintext: Buffer.from(plaintext, 'utf8').toString('base64'),
      additionalAuthenticatedData: Buffer.from(aad, 'utf8').toString('base64'),
    },
  });
  return response.data.ciphertext;
}

export async function decryptSecret(ciphertext: string, aad: string, purpose: 'youtube' | 'connections' = 'youtube'): Promise<string> {
  const client = await auth.getClient();
  const response = await client.request<{ plaintext: string }>({
    url: `https://cloudkms.googleapis.com/v1/${kmsKeyName(purpose)}:decrypt`,
    method: 'POST',
    data: {
      ciphertext,
      additionalAuthenticatedData: Buffer.from(aad, 'utf8').toString('base64'),
    },
  });
  return Buffer.from(response.data.plaintext, 'base64').toString('utf8');
}
