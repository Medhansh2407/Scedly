import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Scedly — Natural-language scheduling that adapts',
  description: 'Turn tasks, deadlines, energy preferences, and availability into an intelligent calendar that repairs itself when plans change.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
        <script dangerouslySetInnerHTML={{ __html: `try{const t=localStorage.getItem('scedly-theme');if(t==='light')document.documentElement.classList.replace('dark','light')}catch{}` }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
