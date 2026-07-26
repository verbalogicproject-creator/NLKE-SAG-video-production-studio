import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';

if (process.platform === 'android') {
  const message = 'Playwright browser execution is unsupported on Android/Termux; run this gate in Linux CI or staging.';
  if (process.env.E2E_REQUIRE_BROWSER === '1') {
    console.error(message);
    process.exit(1);
  }
  console.log(`SKIP: ${message}`);
  process.exit(0);
}

const require = createRequire(import.meta.url);
const cli = require.resolve('@playwright/test/cli');
const forwarded = process.argv.slice(2);
if (forwarded[0] === '--') forwarded.shift();
const result = spawnSync(process.execPath, [cli, 'test', ...forwarded], { stdio: 'inherit' });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
