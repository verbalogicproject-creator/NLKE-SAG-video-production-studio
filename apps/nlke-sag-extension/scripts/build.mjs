import { cp, mkdir, rm } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = resolve(root, 'dist');
await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await cp(resolve(root, 'manifest.json'), resolve(output, 'manifest.json'));
for (const file of ['background.js', 'observer.js', 'overlay.js', 'overlay.css']) {
  await cp(resolve(root, 'src', file), resolve(output, file));
}
console.log(`Built unpacked extension at ${output}`);
