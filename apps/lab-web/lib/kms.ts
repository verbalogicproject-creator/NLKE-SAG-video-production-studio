import { GoogleAuth } from 'google-auth-library';

const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });

function keyName(): string {
  if (!process.env.YOUTUBE_KMS_KEY) throw new Error('YOUTUBE_KMS_KEY is required');
  return process.env.YOUTUBE_KMS_KEY;
}

export async function encryptSecret(plaintext: string, aad: string): Promise<string> {
  const client = await auth.getClient();
  const response = await client.request<{ ciphertext: string }>({
    url: `https://cloudkms.googleapis.com/v1/${keyName()}:encrypt`,
    method: 'POST',
    data: {
      plaintext: Buffer.from(plaintext, 'utf8').toString('base64'),
      additionalAuthenticatedData: Buffer.from(aad, 'utf8').toString('base64'),
    },
  });
  return response.data.ciphertext;
}

export async function decryptSecret(ciphertext: string, aad: string): Promise<string> {
  const client = await auth.getClient();
  const response = await client.request<{ plaintext: string }>({
    url: `https://cloudkms.googleapis.com/v1/${keyName()}:decrypt`,
    method: 'POST',
    data: {
      ciphertext,
      additionalAuthenticatedData: Buffer.from(aad, 'utf8').toString('base64'),
    },
  });
  return Buffer.from(response.data.plaintext, 'base64').toString('utf8');
}
