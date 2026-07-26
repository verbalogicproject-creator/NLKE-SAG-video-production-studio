import { createHash, randomUUID } from 'node:crypto';
import { openAsBlob } from 'node:fs';
import { readFile, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';

const configPath = process.argv[2];
if (!configPath) throw new Error('usage: node scripts/cloud-acceptance.mjs acceptance.json');
const config = JSON.parse(await readFile(configPath, 'utf8'));
const baseUrl = String(config.baseUrl).replace(/\/$/, '');
const cookie = process.env.SAG_ACCEPTANCE_COOKIE;
const apiKey = process.env.SAG_ACCEPTANCE_API_KEY;
if (!cookie || !apiKey) throw new Error('SAG_ACCEPTANCE_COOKIE and SAG_ACCEPTANCE_API_KEY are required');

const restHeaders = { cookie, 'content-type': 'application/json' };

async function jsonFetch(url, init = {}) {
  const response = await fetch(url, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${init.method ?? 'GET'} ${url} failed (${response.status}): ${JSON.stringify(body)}`);
  return body;
}

async function poll(label, operation, done, timeoutMs = 90 * 60_000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const value = await operation();
    if (done(value)) return value;
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
  throw new Error(`${label} timed out after ${timeoutMs}ms`);
}

let rpcId = 0;
async function mcp(name, args) {
  const response = await jsonFetch(`${baseUrl}/api/mcp`, {
    method: 'POST', headers: { authorization: `Bearer ${apiKey}`, 'content-type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: ++rpcId, method: 'tools/call', params: { name, arguments: args } }),
  });
  if (response.error) throw new Error(`MCP ${name}: ${response.error.message}`);
  return JSON.parse(response.result.content[0].text);
}

async function upload(projectId, fixture) {
  const details = await stat(fixture.path);
  const issued = await jsonFetch(`${baseUrl}/api/projects/${projectId}/assets/upload-url`, {
    method: 'POST', headers: restHeaders,
    body: JSON.stringify({ filename: path.basename(fixture.path), contentType: fixture.contentType, sizeBytes: details.size }),
  });
  const blob = await openAsBlob(fixture.path, { type: fixture.contentType });
  const uploaded = await fetch(issued.sessionUri, {
    method: 'PUT', headers: { 'content-type': fixture.contentType, 'content-length': String(details.size) }, body: blob,
  });
  if (!uploaded.ok) throw new Error(`GCS resumable upload failed (${uploaded.status}): ${await uploaded.text()}`);
  await jsonFetch(`${baseUrl}/api/assets/ingest`, {
    method: 'POST', headers: restHeaders,
    body: JSON.stringify({ uploadSessionId: issued.uploadSessionId, generation: uploaded.headers.get('x-goog-generation') ?? undefined }),
  });
  await poll('intake', () => jsonFetch(`${baseUrl}/api/projects/${projectId}`, { headers: { cookie } }),
    (body) => body.project.assets.some((asset) => asset.id === issued.assetId && asset.verifiedAt));
  return issued.assetId;
}

async function creatorLoop(fixture, index) {
  const created = await jsonFetch(`${baseUrl}/api/projects`, {
    method: 'POST', headers: restHeaders,
    body: JSON.stringify({ name: `Cloud acceptance ${fixture.language} ${new Date().toISOString()}` }),
  });
  const assetId = await upload(created.project.id, fixture);
  const analysisRequestId = `acceptance-analysis-${randomUUID()}`;
  const analysisBody = { sourceAssetId: assetId, language: fixture.language, requestId: analysisRequestId };
  const started = await jsonFetch(`${baseUrl}/api/projects/${created.project.id}/chamber`, {
    method: 'POST', headers: restHeaders,
    body: JSON.stringify(analysisBody),
  });
  const duplicateStart = await jsonFetch(`${baseUrl}/api/projects/${created.project.id}/chamber`, {
    method: 'POST', headers: restHeaders, body: JSON.stringify(analysisBody),
  });
  if (duplicateStart.job.id !== started.job.id) throw new Error('analysis request was not idempotent');
  const runId = started.run.id;
  const reviewed = await poll('analysis', () => jsonFetch(`${baseUrl}/api/chamber/${runId}`, { headers: { cookie } }),
    (body) => ['DRAFTS_READY', 'FAILED', 'HALTED_BRAND_VIOLATION'].includes(body.run.status));
  if (reviewed.run.status !== 'DRAFTS_READY') throw new Error(`analysis failed: ${JSON.stringify(reviewed.run)}`);
  const variants = reviewed.run.variants;
  if (variants.length !== 3 || new Set(variants.map((entry) => entry.suggestionId)).size !== 3) {
    throw new Error('analysis did not produce three distinct platform drafts');
  }
  const chosen = 'YT_SHORTS_9_16';
  await jsonFetch(`${baseUrl}/api/chamber/${runId}/variants/${chosen}/accept`, {
    method: 'POST', headers: restHeaders, body: JSON.stringify({ name: `${fixture.language} verified draft` }),
  });
  const canonical = await mcp('project.get', { runId, variant: chosen });
  const title = canonical.project.tracks.flatMap((track) => track.items).find((item) => item.kind === 'title');
  if (!title) throw new Error('accepted draft has no focused-edit title target');
  const edit = await mcp('focused_edit.apply', {
    runId, variant: chosen, command: 'timeline.set_title',
    arguments: { item_id: title.id, text: fixture.hookTitle },
    expectedRevision: canonical.project.revision, requestId: `acceptance-edit-${randomUUID()}`,
  });
  const revision = edit.project?.revision ?? edit.project_revision ?? canonical.project.revision + 1;
  const renderRequestId = `acceptance-render-${randomUUID()}`;
  const renderInput = { runId, variant: chosen, projectRevision: revision, requestId: renderRequestId };
  const firstRender = await mcp('render.start', renderInput);
  const duplicateRender = await mcp('render.start', renderInput);
  if (duplicateRender.payload.job_id !== firstRender.payload.job_id) throw new Error('render request was not idempotent');
  const rendered = await poll('render and observation', () => mcp('drafts.review', { runId }),
    (run) => run.variants.some((entry) => entry.variant === chosen && ['READY_TO_PUBLISH', 'FAILED'].includes(entry.status)));
  const deliverable = rendered.variants.find((entry) => entry.variant === chosen);
  if (deliverable.status !== 'READY_TO_PUBLISH' || !deliverable.deliverableAssetId) {
    throw new Error(`render was not independently verified: ${JSON.stringify(deliverable)}`);
  }
  const download = await mcp('download.create', { artifactAssetId: deliverable.deliverableAssetId });
  const response = await fetch(download.url);
  if (!response.ok || !response.body) throw new Error(`signed download failed: ${response.status}`);
  const digest = createHash('sha256');
  for await (const chunk of response.body) digest.update(chunk);
  if (digest.digest('hex') !== download.sha256) throw new Error('signed download hash differs from verified artifact');
  return { language: fixture.language, projectId: created.project.id, runId, artifactAssetId: deliverable.deliverableAssetId, sha256: download.sha256 };
}

const fixtures = [config.fixtures.english, config.fixtures.hebrew];
const results = [];
for (let index = 0; index < fixtures.length; index += 1) results.push(await creatorLoop(fixtures[index], index));
const report = { completedAt: new Date().toISOString(), baseUrl, results, passed: true };
const reportPath = config.reportFile ?? 'cloud-acceptance-report.json';
await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report, null, 2));
