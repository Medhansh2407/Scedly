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
        <script dangerouslySetInnerHTML={{ __html: `try{const t=localStorage.getItem('scedly-theme');if(t==='light')document.documentElement.classList.replace('dark','light')}catch{}` }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
