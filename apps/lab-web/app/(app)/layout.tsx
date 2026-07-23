import { TimecodeBar } from '@/components/lab/TimecodeBar';

// Authenticated shell — wraps every /dashboard, /projects, /brand, /connections page.
// Keeps the top-strip + bottom-bar rhythm consistent across the whole Lab.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-[100dvh] flex flex-col bg-bg-0">
      <TimecodeBar workspace="Verbalogix" channel="01/04" live />
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  );
}
