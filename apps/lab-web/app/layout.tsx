import type { Metadata } from 'next';
import '@/styles/globals.css';

export const metadata: Metadata = {
  title: {
    default: 'VERBALOGIX · LAB',
    template: '%s · VERBALOGIX LAB',
  },
  description: 'Claude-operated video editing lab. One upload, every platform.',
  metadataBase: new URL('https://lab.verbalogix.com'),
  robots: {
    index: false, // closed beta — do not index
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
