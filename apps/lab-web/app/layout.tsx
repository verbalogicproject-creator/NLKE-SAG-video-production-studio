import type { Metadata } from 'next';
import '@/styles/globals.css';

export const metadata: Metadata = {
  title: {
    default: 'SAG Video Chamber',
    template: '%s | SAG Video Chamber',
  },
  description: 'Create, refine, and independently verify three platform-specific vertical video drafts.',
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
