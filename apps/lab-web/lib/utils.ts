import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format milliseconds as HH:MM:SS.mmm */
export function formatTimecode(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '00:00:00.000';
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const msPart = ms % 1000;
  const pad = (n: number, w = 2) => n.toString().padStart(w, '0');
  return `${pad(h)}:${pad(m)}:${pad(s)}.${pad(msPart, 3)}`;
}

/** Short ETA: "0:42", "1:04", "12:38" */
export function formatEta(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '—:—';
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

/** Bytes → human label ("1.4 GB", "320 MB") */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const idx = Math.min(i, units.length - 1);
  return `${(bytes / Math.pow(k, idx)).toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}
