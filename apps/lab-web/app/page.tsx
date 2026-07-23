import Link from 'next/link';

export default function LandingPage() {
  return (
    <main className="relative min-h-[100dvh] flex flex-col">
      <header className="flex items-center justify-between px-6 py-4 hairline">
        <span className="data text-xs text-ink-1">SAG VIDEO CHAMBER</span>
        <nav className="flex items-center gap-6">
          <Link
            href="/dashboard"
            className="data text-xs text-bg-0 bg-amber px-3 py-1.5 hover:bg-amber-hot"
          >
            LOG IN
          </Link>
        </nav>
      </header>

      <section className="flex-1 flex items-center justify-center px-6">
        <div className="max-w-3xl text-center">
          <p className="data text-xs text-amber mb-4">INVITE-ONLY BETA</p>
          <h1 className="font-display text-5xl md:text-7xl font-medium leading-[1.05] mb-6">
            One source.
            <br />
            Three sharp cuts.
          </h1>
          <p className="text-lg text-ink-1 max-w-xl mx-auto mb-10">
            Create, refine, verify, and privately publish vertical video without losing the source trail.
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link
              href="/dashboard"
              className="data text-xs bg-amber text-bg-0 px-5 py-3 hover:bg-amber-hot"
            >
              OPEN CHAMBER
            </Link>
          </div>
        </div>
      </section>

      <footer className="px-6 py-4 hairline flex items-center justify-between">
        <span className="data text-[10px] text-ink-3">VERIFIED OUTPUT</span>
        <span className="data text-[10px] text-ink-3">
          SAG VIDEO {new Date().getFullYear()}
        </span>
      </footer>
    </main>
  );
}
