'use client';
import { useState } from 'react';

interface Props { onSend: (msg: string) => void; disabled?: boolean; }

export default function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState('');

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const msg = value.trim();
    if (!msg || disabled) return;
    onSend(msg);
    setValue('');
  }

  return (
    <form onSubmit={submit} className="border-t border-border bg-terminal p-3 shrink-0">
      <div className="flex items-center gap-2 bg-surface border border-border rounded-[10px] px-3 py-2.5 focus-within:border-cyan focus-within:shadow-[0_0_0_2px_rgba(79,195,247,.07)] transition-all duration-150">
        <span className="font-mono text-[12px] font-medium text-cyan whitespace-nowrap">scedly&gt;</span>
        <input value={value} onChange={e => setValue(e.target.value)} disabled={disabled} placeholder="schedule something, or ask why a task is where it is…" className="flex-1 bg-transparent font-mono text-[12px] text-white placeholder:text-text-tertiary outline-none" />
        <button type="submit" disabled={!value.trim() || disabled} className="px-2.5 py-1 rounded-md bg-cyan text-black text-[11px] font-bold opacity-85 hover:opacity-100 hover:shadow-[0_2px_6px_rgba(79,195,247,.25)] disabled:opacity-30 transition-all duration-150">send</button>
      </div>
    </form>
  );
}
