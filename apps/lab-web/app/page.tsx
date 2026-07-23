import Link from 'next/link';

// Marketing landing — pre-auth. Minimal, Cutting Room aesthetic applied
// even here so the brand reads continuously from landing → app.
export default function LandingPage() {
  return (
    <main className="relative min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-6 py-4 hairline">
        <span className="data text-xs text-ink-1">VERBALOGIX · LAB</span>
        <nav className="flex items-center gap-6">
          <Link href="/pricing" className="data text-xs text-ink-1 hover:text-amber">
            PRICING
          </Link>
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
          <p className="data text-xs text-amber mb-4">CLOSED BETA · 2026</p>
          <h1 className="font-display text-5xl md:text-7xl font-medium leading-[1.05] mb-6">
            One upload.
            <br />
            Every platform.
          </h1>
          <p className="text-lg text-ink-1 max-w-xl mx-auto mb-10">
            A Claude-operated video editing lab. Drop raw footage, get
            per-platform edits with runtime brand enforcement.
            YouTube, LinkedIn, TikTok, Instagram, Facebook.
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link
              href="/dashboard"
              className="data text-xs bg-amber text-bg-0 px-5 py-3 hover:bg-amber-hot"
            >
              ENTER LAB →
            </Link>
            <Link
              href="/pricing"
              className="data text-xs text-ink-1 px-5 py-3 hairline hover:text-amber hover:shadow-[inset_0_0_0_1px_rgb(var(--amber))]"
            >
              SEE PRICING
            </Link>
          </div>
        </div>
      </section>

      <footer className="px-6 py-4 hairline flex items-center justify-between">
        <span className="data text-[10px] text-ink-3">
          SYSTEM · BETA · v0.1.0
        </span>
        <span className="data text-[10px] text-ink-3">
          VERBALOGIX · {new Date().getFullYear()}
        </span>
      </footer>
    </main>
  );
}
