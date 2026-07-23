'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export function NewProjectButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function create() {
    const name = window.prompt('Project name');
    if (!name) return;
    setBusy(true);
    const response = await fetch('/api/projects', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name }) });
    const body = await response.json();
    setBusy(false);
    if (!response.ok) return window.alert(body.message ?? body.error);
    router.push(`/projects/${body.project.id}`);
    router.refresh();
  }
  return <button type="button" disabled={busy} onClick={create} className="data text-[11px] bg-amber text-bg-0 px-3 py-1.5 hover:bg-amber-hot disabled:opacity-50">{busy ? 'CREATING…' : '+ NEW PROJECT'}</button>;
}
