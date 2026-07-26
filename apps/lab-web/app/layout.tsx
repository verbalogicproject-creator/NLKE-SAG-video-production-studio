import type { Metadata } from 'next';
import '@/styles/globals.css';

export const metadata: Metadata = {
  title: {
    default: 'SAG Video by Verbalogix',
    template: '%s | SAG Video',
  },
  description: 'A governed video production studio for direct editing and Codex-operated workflows.',
  metadataBase: new URL('https://lab.verbalogix.com'),
  robots: {
    index: false,
    follow: false,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full bg-bg-0 text-ink-0">
      <body className="h-full antialiased selection:bg-amber/30">
        {children}
      </body>
    </html>
  );
}
