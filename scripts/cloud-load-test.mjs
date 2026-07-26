import { randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';

const configPath = process.argv[2];
if (!configPath) throw new Error('usage: node scripts/cloud-load-test.mjs load-test.json');
const config = JSON.parse(await readFile(configPath, 'utf8'));
if (!Array.isArray(config.workspaces) || config.workspaces.length !== 10) throw new Error('load test requires exactly ten workspace entries');
const baseUrl = String(config.baseUrl).replace(/\/$/, '');

async function mcp(entry, name, args) {
  const response = await fetch(`${baseUrl}/api/mcp`, {
    method: 'POST', headers: { authorization: `Bearer ${entry.apiKey}`, 'content-type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: randomUUID(), method: 'tools/call', params: { name, arguments: args } }),
  });
  const body = await response.json();
  if (!response.ok || body.error) throw new Error(`${entry.name} ${name}: ${body.error?.message ?? response.status}`);
  return JSON.parse(body.result.content[0].text);
}

// Prove one workspace key cannot inspect another workspace's run.
const isolationProbe = await fetch(`${baseUrl}/api/mcp`, {
  method: 'POST', headers: { authorization: `Bearer ${config.workspaces[0].apiKey}`, 'content-type': 'application/json' },
  body: JSON.stringify({ jsonrpc: '2.0', id: randomUUID(), method: 'tools/call', params: {
    name: 'drafts.review', arguments: { runId: config.workspaces[1].runId },
  } }),
}).then((response) => response.json());
if (!isolationProbe.error) throw new Error('cross-workspace run discovery was not denied');

const startedAt = new Date().toISOString();
await Promise.all(config.workspaces.map((entry) => mcp(entry, 'render.start', {
  runId: entry.runId, variant: entry.variant, projectRevision: entry.projectRevision,
  requestId: `load-render-${randomUUID()}`,
})));

const completed = new Map();
let maximumObservedHeavy = 0;
const deadline = Date.now() + Number(config.timeoutMs ?? 90 * 60_000);
while (completed.size < config.workspaces.length && Date.now() < deadline) {
  const runs = await Promise.all(config.workspaces.map((entry) => mcp(entry, 'drafts.review', { runId: entry.runId })));
  const queue = await mcp(config.workspaces[0], 'operations.queue', {});
  if (queue.activeHeavy > queue.configuredHeavyLimit) {
    throw new Error(`global heavy limit exceeded: ${queue.activeHeavy}/${queue.configuredHeavyLimit}`);
  }
  maximumObservedHeavy = Math.max(maximumObservedHeavy, queue.activeHeavy);
  runs.forEach((run, index) => {
    const entry = config.workspaces[index];
    const variant = run.variants.find((candidate) => candidate.variant === entry.variant);
    if (variant?.status === 'FAILED') throw new Error(`${entry.name} render failed: ${JSON.stringify(variant)}`);
    if (variant?.status === 'READY_TO_PUBLISH' && !completed.has(entry.name)) completed.set(entry.name, new Date().toISOString());
  });
  await new Promise((resolve) => setTimeout(resolve, 3000));
}
if (completed.size !== 10) throw new Error(`only ${completed.size}/10 workspaces completed before timeout`);
const report = {
  startedAt, completedAt: new Date().toISOString(), passed: true,
  crossWorkspaceDenied: true, configuredHeavyLimit: 2, maximumHeavyObserved: maximumObservedHeavy,
  completionOrder: [...completed.entries()].map(([workspace, at]) => ({ workspace, at })),
};
await writeFile(config.reportFile ?? 'cloud-load-report.json', `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report, null, 2));
