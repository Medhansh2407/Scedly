'use client';
import { useEffect, useState } from 'react';

interface Props { startHour?: number; hourHeight?: number; }

export default function NowIndicator({ startHour = 8, hourHeight = 66 }: Props) {
  const [top, setTop] = useState<number | null>(null);
  const [time, setTime] = useState('');

  useEffect(() => {
    function calc() {
      const now = new Date();
      const h = now.getHours() + now.getMinutes() / 60;
      if (h < startHour || h > 22) { setTop(null); return; }
      setTop((h - startHour) * hourHeight);
      setTime(now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }));
    }
    calc();
    const id = setInterval(calc, 30_000);
    return () => clearInterval(id);
  }, [startHour, hourHeight]);

  if (top === null) return null;

  return (
    <div className="absolute left-[-6px] right-0 z-20 pointer-events-none flex items-center" style={{ top }}>
      <div className="w-[11px] h-[11px] rounded-full bg-cyan shadow-[0_0_6px_#4FC3F7,0_0_14px_rgba(79,195,247,.3)] animate-[nowPulse_2s_ease-in-out_infinite]" />
      <div className="flex-1 h-[2px] bg-gradient-to-r from-cyan via-cyan/10 to-transparent" style={{ backgroundSize: '100%', backgroundPosition: '0 0' }} />
      <span className="absolute right-2 font-mono text-[10px] text-cyan bg-bg px-1.5 py-px rounded-sm border border-cyan/15">{time}</span>
    </div>
  );
}
