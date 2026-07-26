const FALLBACK_LIMIT = 96 * 1024 * 1024;
const DIRECTORY = 'sag-video-capture-spool';

export type CompletedCapture = {
  blob: Blob;
  fileName: string;
  cleanup: () => Promise<void>;
};

export type CaptureSpool = {
  append: (blob: Blob) => Promise<void>;
  finish: () => Promise<CompletedCapture>;
  persistent: boolean;
};

type DirectoryHandle = {
  getDirectoryHandle(name: string, options?: { create?: boolean }): Promise<DirectoryHandle>;
  getFileHandle(name: string, options?: { create?: boolean }): Promise<any>;
  removeEntry(name: string): Promise<void>;
  values(): AsyncIterable<any>;
};

async function spoolDirectory(): Promise<DirectoryHandle | null> {
  const storage = navigator.storage as StorageManager;
  const getDirectory = (storage as StorageManager & { getDirectory?: () => Promise<unknown> }).getDirectory;
  if (!getDirectory) return null;
  const root = await getDirectory.call(storage) as DirectoryHandle;
  return root.getDirectoryHandle(DIRECTORY, { create: true });
}

export async function createCaptureSpool(name: string, mimeType: string): Promise<CaptureSpool> {
  const directory = await spoolDirectory().catch(() => null);
  const fileName = `${Date.now()}-${crypto.randomUUID()}-${name}.webm`;
  if (directory) {
    const handle = await directory.getFileHandle(fileName, { create: true });
    let position = 0;
    return {
      persistent: true,
      async append(blob) {
        const writer = await handle.createWritable({ keepExistingData: true });
        await writer.write({ type: 'write', position, data: blob });
        position += blob.size;
        await writer.close();
      },
      async finish() {
        const file = await handle.getFile();
        return {
          blob: file.slice(0, file.size, mimeType || file.type || 'video/webm'), fileName,
          cleanup: () => directory.removeEntry(fileName),
        };
      },
    };
  }

  const chunks: Blob[] = [];
  let bytes = 0;
  return {
    persistent: false,
    async append(blob) {
      bytes += blob.size;
      if (bytes > FALLBACK_LIMIT) throw new Error('Capture memory fallback reached its 96 MB limit.');
      chunks.push(blob);
    },
    async finish() {
      return { blob: new Blob(chunks, { type: mimeType || 'video/webm' }), fileName, cleanup: async () => undefined };
    },
  };
}

export async function recoverCaptureSpools(): Promise<CompletedCapture[]> {
  const directory = await spoolDirectory().catch(() => null);
  if (!directory) return [];
  const recovered: CompletedCapture[] = [];
  for await (const handle of directory.values()) {
    if (handle.kind !== 'file') continue;
    const file = await handle.getFile();
    if (!file.size) continue;
    recovered.push({
      blob: file, fileName: handle.name,
      cleanup: () => directory.removeEntry(handle.name),
    });
  }
  return recovered;
}
