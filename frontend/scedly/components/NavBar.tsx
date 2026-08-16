'use client';

interface NavBarProps {
  displayName?: string;
  avatarUrl?: string;
  trialDaysLeft?: number;
}

export default function NavBar({ displayName, avatarUrl, trialDaysLeft }: NavBarProps) {
  const initials = (displayName || '?').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

  return (
    <nav className="h-[52px] flex items-center justify-between px-4 bg-surface border-b border-border shrink-0">
      <div className="flex items-center gap-1">
        <span className="font-mono text-[15px] font-semibold text-cyan mr-4">🌙 scedly</span>
        <a href="/app" className="text-[13px] text-white bg-white/[.06] rounded-lg px-3 py-1.5 transition-all duration-150">workspace</a>
        <a href="/settings" className="text-[13px] text-text-tertiary hover:text-white px-3 py-1.5 transition-all duration-150">settings</a>
      </div>
      <div className="flex items-center gap-3">
        {trialDaysLeft !== undefined && trialDaysLeft > 0 && (
          <span className="flex items-center gap-1.5 text-[11px] text-green border border-green/30 rounded-full px-3 py-1">
            <span className="w-1.5 h-1.5 rounded-full bg-green shadow-[0_0_4px_#66BB6A]" />
            Pro trial · {trialDaysLeft} days
          </span>
        )}
        <button onClick={() => { const next = document.documentElement.classList.toggle('light') ? 'light' : 'dark'; localStorage.setItem('scedly-theme', next); }} className="w-8 h-8 rounded-[9px] border border-border flex items-center justify-center text-[14px] hover:bg-white/[.04] transition-all duration-150" title="Toggle theme">
          <span className="dark:hidden">🌙</span><span className="hidden dark:inline">☀️</span>
        </button>
        <div className="w-8 h-8 rounded-[9px] bg-gradient-to-br from-cyan to-[#7C4DFF] flex items-center justify-center text-[11px] font-bold text-white">
          {avatarUrl ? (
            // Remote OAuth avatar hosts vary by provider and cannot be safely
            // allow-listed for Next's image optimizer.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={avatarUrl} alt="" className="w-full h-full rounded-[9px] object-cover" />
          ) : initials}
        </div>
      </div>
    </nav>
  );
}
